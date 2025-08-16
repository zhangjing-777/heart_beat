from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import psycopg
from psycopg.rows import dict_row
import asyncio
from datetime import datetime, timezone, timedelta
import logging
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 数据库配置
DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

# Pydantic模型
class HeartBeatInput(BaseModel):
    ip_address: str
    mac_address: str
    sn: str
    beat_time: str  # ISO格式时间字符串

class HeartBeatUpdate(BaseModel):
    ip_address: Optional[str] = None
    sn: Optional[str] = None
    beat_time: Optional[str] = None

class UpdateResponse(BaseModel):
    updated_fields: List[str]
    message: str

class DeviceStatus(BaseModel):
    id: int
    mac_address: str
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    status: str
    location: Optional[str] = None
    create_time: Optional[str] = None
    last_heartbeat: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    database: str
    connection_mode: str
    monitor_task: str
    timestamp: str

class MonitorControlResponse(BaseModel):
    action: str
    status: str
    message: str
    timestamp: str

# 全局变量
monitor_task = None
monitor_enabled = True  # 添加监听控制标志

async def create_connection():
    """创建新的数据库连接"""
    try:
        conn = await psycopg.AsyncConnection.connect(**DATABASE_CONFIG)
        # 设置行工厂为字典格式
        conn.row_factory = dict_row
        return conn
    except Exception as e:
        logger.error(f"创建数据库连接失败: {e}")
        raise

async def close_connection(conn):
    """关闭数据库连接"""
    if conn and not conn.closed:
        try:
            await conn.close()
        except Exception as e:
            logger.error(f"关闭数据库连接失败: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动阶段
    logger.info("正在启动应用...")
    
    try:
        # 测试数据库连接
        test_conn = await create_connection()
        async with test_conn.cursor() as cur:
            await cur.execute("SELECT version()")
            result = await cur.fetchone()
        await close_connection(test_conn)
        logger.info(f"数据库连接测试成功: {result['version'][:50]}...")
        
        # 启动监控任务
        monitor_task = asyncio.create_task(monitor_heartbeat_task())
        app.state.monitor_task = monitor_task
        logger.info("心跳监控任务启动")
        logger.info("应用启动完成")
        
        yield  # 应用运行阶段
        
    except Exception as e:
        logger.error(f"应用启动失败: {e}")
        raise
    finally:
        # 关闭阶段
        logger.info("正在关闭应用...")
        
        # 停止监控任务
        if hasattr(app.state, 'monitor_task') and not app.state.monitor_task.done():
            app.state.monitor_task.cancel()
            try:
                await app.state.monitor_task
            except asyncio.CancelledError:
                logger.info("心跳监控任务已停止")

app = FastAPI(title="Heart Beat Monitor API", version="1.0.0", lifespan=lifespan)


@app.post("/heartbeat", response_model=Dict[str, Any], tags=["心跳管理"])
async def create_or_update_heartbeat(heartbeat: HeartBeatInput):
    """
    创建或更新心跳记录
    
    根据MAC地址查看是否存在记录：
    - 如果不存在则创建新记录
    - 如果存在则只更新beat_time字段
    
    返回device_map表中对应的设备信息
    """
    conn = None
    try:
        conn = await create_connection()
        
        # 解析时间
        beat_time = datetime.fromisoformat(heartbeat.beat_time.replace('Z', '+00:00'))
        
        # 使用事务确保数据一致性
        async with conn.transaction():
            # 检查记录是否存在
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM heart_beat WHERE mac_address = %s",
                    (heartbeat.mac_address,)
                )
                existing_record = await cur.fetchone()
            
            if existing_record:
                # 更新beat_time
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE heart_beat SET beat_time = %s WHERE mac_address = %s",
                        (beat_time, heartbeat.mac_address)
                    )
                logger.info(f"更新心跳记录: {heartbeat.mac_address}")
            else:
                # 插入新记录
                async with conn.cursor() as cur:
                    await cur.execute(
                        """INSERT INTO heart_beat (ip_address, mac_address, sn, beat_time) 
                           VALUES (%s, %s, %s, %s)""",
                        (heartbeat.ip_address, heartbeat.mac_address, 
                         heartbeat.sn, beat_time)
                    )
                logger.info(f"创建新心跳记录: {heartbeat.mac_address}")
            
            # 查询device_map表信息 - 使用SELECT *
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM device_map WHERE mac_address = %s",
                    (heartbeat.mac_address,)
                )
                device_info = await cur.fetchone()
            
            if device_info:
                return device_info
            else:
                return {
                    "message": "Heart beat recorded, but device not found in device_map",
                    "mac_address": heartbeat.mac_address
                }
                
    except Exception as e:
        logger.error(f"创建/更新心跳记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await close_connection(conn)

@app.get("/heartbeat/{mac_address}")
async def get_heartbeat(mac_address: str):
    """根据MAC地址查询心跳记录"""
    conn = None
    try:
        conn = await create_connection()
        
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT id, ip_address, mac_address, sn, beat_time, create_time 
                   FROM heart_beat WHERE mac_address = %s""",
                (mac_address,)
            )
            record = await cur.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail="Heart beat record not found")
        
        return record
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询心跳记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await close_connection(conn)

@app.get("/heartbeat")
async def list_heartbeats(limit: int = 100, offset: int = 0):
    """获取所有心跳记录"""
    conn = None
    try:
        conn = await create_connection()
        
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT id, ip_address, mac_address, sn, beat_time, create_time 
                   FROM heart_beat ORDER BY beat_time DESC LIMIT %s OFFSET %s""",
                (limit, offset)
            )
            records = await cur.fetchall()
        
        return records
        
    except Exception as e:
        logger.error(f"查询心跳记录列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await close_connection(conn)

@app.put("/heartbeat/{mac_address}", response_model=UpdateResponse)
async def update_heartbeat(mac_address: str, update_data: HeartBeatUpdate):
    """更新心跳记录"""
    conn = None
    try:
        conn = await create_connection()
        
        async with conn.transaction():
            # 检查记录是否存在
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM heart_beat WHERE mac_address = %s",
                    (mac_address,)
                )
                existing_record = await cur.fetchone()
            
            if not existing_record:
                raise HTTPException(status_code=404, detail="Heart beat record not found")
            
            # 构建更新字段
            update_fields = []
            update_values = []
            updated_field_names = []
            
            if update_data.ip_address is not None:
                update_fields.append(f"ip_address = %s")
                update_values.append(update_data.ip_address)
                updated_field_names.append("ip_address")
            
            if update_data.sn is not None:
                update_fields.append(f"sn = %s")
                update_values.append(update_data.sn)
                updated_field_names.append("sn")
            
            if update_data.beat_time is not None:
                beat_time = datetime.fromisoformat(update_data.beat_time.replace('Z', '+00:00'))
                update_fields.append(f"beat_time = %s")
                update_values.append(beat_time)
                updated_field_names.append("beat_time")
            
            if not update_fields:
                raise HTTPException(status_code=400, detail="No fields to update")
            
            # 执行更新
            update_values.append(mac_address)
            query = f"UPDATE heart_beat SET {', '.join(update_fields)} WHERE mac_address = %s"
            
            async with conn.cursor() as cur:
                await cur.execute(query, update_values)
            
            return UpdateResponse(
                updated_fields=updated_field_names,
                message=f"Successfully updated {len(updated_field_names)} field(s)"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新心跳记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await close_connection(conn)

@app.delete("/heartbeat/{mac_address}")
async def delete_heartbeat(mac_address: str):
    """删除心跳记录"""
    conn = None
    try:
        conn = await create_connection()
        
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM heart_beat WHERE mac_address = %s",
                (mac_address,)
            )
            
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Heart beat record not found")
        
        return {"message": f"Heart beat record for MAC {mac_address} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除心跳记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await close_connection(conn)

async def monitor_heartbeat_task():
    """
    监听心跳超时任务
    检查beat_time超过5分钟的记录，将对应设备状态设为offline
    """
    global monitor_enabled
    logger.info("心跳监听任务启动")
    
    while True:
        conn = None
        try:
            # 检查是否被禁用
            if not monitor_enabled:
                logger.info("心跳监听已被禁用，等待重新启用...")
                await asyncio.sleep(10)
                continue
            
            conn = await create_connection()
            
            # 计算5分钟前的时间
            timeout_threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
            
            # 使用事务确保数据一致性
            async with conn.transaction():
                # 查找超时的设备
                async with conn.cursor() as cur:
                    await cur.execute(
                        """SELECT DISTINCT h.mac_address 
                           FROM heart_beat h
                           INNER JOIN device_map d ON h.mac_address = d.mac_address
                           WHERE h.beat_time < %s AND d.status != 'offline'""",
                        (timeout_threshold,)
                    )
                    timeout_devices = await cur.fetchall()
                
                offline_count = 0
                for device in timeout_devices:
                    mac_address = device['mac_address']
                    
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE device_map SET status = 'offline' WHERE mac_address = %s",
                            (mac_address,)
                        )
                        
                        if cur.rowcount > 0:
                            offline_count += 1
                            logger.info(f"设备 {mac_address} 心跳超时，状态更新为offline")
                
                # 查找最近5分钟内有心跳的设备
                async with conn.cursor() as cur:
                    await cur.execute(
                        """SELECT DISTINCT h.mac_address 
                           FROM heart_beat h
                           INNER JOIN device_map d ON h.mac_address = d.mac_address
                           WHERE h.beat_time >= %s AND d.status = 'offline'""",
                        (timeout_threshold,)
                    )
                    online_devices = await cur.fetchall()
                
                online_count = 0
                for device in online_devices:
                    mac_address = device['mac_address']
                    
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE device_map SET status = 'online' WHERE mac_address = %s",
                            (mac_address,)
                        )
                        
                        if cur.rowcount > 0:
                            online_count += 1
                            logger.info(f"设备 {mac_address} 心跳恢复，状态更新为online")
                
                # 记录统计信息（只在有变化时记录）
                if offline_count > 0 or online_count > 0:
                    logger.info(f"状态更新完成 - 离线: {offline_count}台, 上线: {online_count}台")
                
        except asyncio.CancelledError:
            logger.info("心跳监控任务被取消")
            break
        except Exception as e:
            logger.error(f"心跳监听任务异常: {e}")
            # 如果是连接问题，等待更长时间后重试
            if "connection" in str(e).lower():
                logger.info("数据库连接异常，等待60秒后重试")
                await asyncio.sleep(60)
                continue
        finally:
            # 确保释放连接
            await close_connection(conn)
        
        # 每30秒检查一次
        await asyncio.sleep(30)

@app.get("/", tags=["系统"])
async def root():
    """健康检查接口"""
    return {
        "message": "Heart Beat Monitor API is running", 
        "timestamp": datetime.now(timezone.utc),
        "version": "1.0.0"
    }

@app.get("/health", response_model=HealthResponse, tags=["系统"])
async def health_check():
    """详细健康检查"""
    conn = None
    try:
        conn = await create_connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
            db_status = await cur.fetchone()
        
        return HealthResponse(
            status="healthy",
            database="connected" if db_status else "error",
            connection_mode="direct",
            monitor_task=f"{'running' if monitor_task and not monitor_task.done() else 'stopped'} ({'enabled' if monitor_enabled else 'disabled'})",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            database=f"error: {str(e)}",
            connection_mode="direct",
            monitor_task="unknown",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    finally:
        await close_connection(conn)

@app.post("/monitor/enable", response_model=MonitorControlResponse, tags=["监听控制"])
async def enable_monitor():
    """
    启用心跳监听功能
    
    启用后，系统将自动监控设备心跳超时情况
    """
    global monitor_enabled
    
    monitor_enabled = True
    logger.info("心跳监听功能已启用")
    
    return MonitorControlResponse(
        action="enable",
        status="success",
        message="心跳监听功能已启用",
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@app.post("/monitor/disable", response_model=MonitorControlResponse, tags=["监听控制"])
async def disable_monitor():
    """
    禁用心跳监听功能
    
    禁用后，系统将停止自动监控设备心跳超时情况
    """
    global monitor_enabled
    
    monitor_enabled = False
    logger.info("心跳监听功能已禁用")
    
    return MonitorControlResponse(
        action="disable",
        status="success",
        message="心跳监听功能已禁用",
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@app.get("/monitor/status", tags=["监听控制"])
async def get_monitor_status():
    """
    获取心跳监听功能状态
    
    返回当前监听功能的启用/禁用状态和任务运行状态
    """
    global monitor_task, monitor_enabled
    
    task_status = "stopped"
    if monitor_task and not monitor_task.done():
        task_status = "running"
    
    return {
        "monitor_enabled": monitor_enabled,
        "task_status": task_status,
        "monitor_status": f"{task_status} ({'enabled' if monitor_enabled else 'disabled'})",
        "message": f"监听功能{'已启用' if monitor_enabled else '已禁用'}，后台任务{'运行中' if task_status == 'running' else '已停止'}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/monitor/restart", response_model=MonitorControlResponse, tags=["监听控制"])
async def restart_monitor():
    """
    重启心跳监听任务
    
    停止当前监听任务并重新启动，用于故障恢复
    """
    global monitor_task, monitor_enabled
    
    try:
        # 停止当前任务
        if monitor_task and not monitor_task.done():
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        
        # 重新启动任务
        monitor_task = asyncio.create_task(monitor_heartbeat_task())
        monitor_enabled = True
        
        logger.info("心跳监听任务已重启")
        
        return MonitorControlResponse(
            action="restart",
            status="success",
            message="心跳监听任务已重启",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
    except Exception as e:
        logger.error(f"重启监听任务失败: {e}")
        return MonitorControlResponse(
            action="restart",
            status="error",
            message=f"重启失败: {str(e)}",
            timestamp=datetime.now(timezone.utc).isoformat()
        )