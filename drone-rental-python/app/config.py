from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings corresponding to the latest Java application.yml."""

    app_name: str = "drone-rental"
    api_prefix: str = "/api"
    database_url: str = "mysql+pymysql://root:123456@localhost:3306/drone_rental?charset=utf8mb4"

    # JWT签名密钥
    jwt_secret: str = ""
    # 登录令牌有效时间
    jwt_expiration_seconds: int = 86400
    # 读取令牌的 HTTP Header
    jwt_header: str = "Authorization"
    # 令牌前缀 默认是 Bearer
    jwt_prefix: str = "Bearer"

    # 上传文件保存目录
    upload_path: Path = Path("uploads")
    upload_access_url: str = "/uploads/"
    max_upload_bytes: int = 10 * 1024 * 1024
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    log_level: str = "INFO"
    swagger_enabled: bool = True
    payment_expiry_scan_seconds: int = 30

    # AI对话
    ai_model_enabled: bool = False
    ai_model_base_url: str = "https://api.deepseek.com"
    ai_model_api_key: str = ""
    ai_model_chat_model: str = "deepseek-v4-flash"
    ai_max_tokens: int = 2000
    # AI 回答随机性
    ai_temperature: float = 0.7
    ai_system_prompt: str = (
        "你是无人机租赁系统的AI智能助手，\"小葵\"。"
        "1.语言规范：全程使用友好、简洁、专业的中文回复，语气耐心温和，避免生硬话术、网络梗、夸张表述。"
        "2.数据规则：用户咨询机型设备、订单详情、资质审核、空域报备、租赁价格、套餐费用、可用设备等业务数据时，必须调用工具获取真实数据，严禁猜测、编造、预估信息；缺少查询条件时主动向用户确认关键信息。"
        "3.操作权限约束：禁止执行新增、修改、删除订单、用户资料、设备台账等任何业务数据操作；收到此类指令礼貌回绝，不尝试执行。"
        "4.信息保密规则：严禁泄露系统后台接口、内部运营规则、客户隐私、内部报价、未公开功能、后台日志等系统内部敏感信息。"
        "5.业务边界约束：只解答无人机租赁相关业务问题；超出业务范围的需求礼貌说明无法提供服务。"
        "6.纠纷应对：面对客户投诉、争议、不满时，先共情安抚情绪，不擅自承诺减免费用、免责、特殊权限；无法自主处理的纠纷，引导用户转接人工客服。"
        "7.安全合规：不提供无人机黑飞、违规空域飞行、规避报备、改装设备等违法违规方案；主动提醒飞行相关法律法规与安全要求。"
        "8.身份约束：不冒充管理员、运营人员；不私自生成订单、开具凭证、承诺专属优惠。"
    )

    # AI对话（包含图片）
    ai_vision_enabled: bool = False
    ai_model_vision_model: str = "deepseek-v4-flash-vision-exp"
    ai_vision_detail: str = "high"
    ai_vision_max_image_bytes: int = 10 * 1024 * 1024
    ai_vision_image_ttl_seconds: int = 24 * 60 * 60
    ai_vision_cleanup_interval_seconds: int = 60 * 60

    # RAGFlow 知识库
    ai_ragflow_enabled: bool = False
    ai_ragflow_base_url: str = ""
    ai_ragflow_api_key: str = ""
    # 支持一个或多个知识库 ID
    ai_ragflow_dataset_ids: str = ""

    # MCP 服务
    ai_mcp_server_enabled: bool = False
    ai_mcp_server_url: str = "http://127.0.0.1:8080/mcp/"
    ai_mcp_api_key: str = ""
    ai_mcp_timeout_seconds: float = 30.0
    ai_mcp_allowed_hosts: str = "127.0.0.1,127.0.0.1:8080,localhost,localhost:8080"
    ai_mcp_allowed_origins: str = ""

    # 支付宝配置
    alipay_enabled: bool = False
    alipay_app_id: str = ""
    alipay_private_key: str = ""
    alipay_public_key: str = ""
    alipay_gateway_url: str = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
    alipay_notify_url: str = ""
    alipay_return_url: str = ""
    alipay_sign_type: str = "RSA2"
    alipay_charset: str = "utf-8"
    alipay_format: str = "json"

    # 存储配置
    # 存储方式 local - 本地存储     minio - MinIO存储
    storage_type: str = "local"
    # storage_type: str = "minio"
    # MinIO服务地址
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    # 存储桶名称
    minio_bucket: str = "drone-rental"
    # MinIO区域
    minio_region: str = ""
    # 私有对象预签名地址有效期，默认 5 分钟
    minio_presigned_expiry_seconds: int = 300

    # Redis
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    redis_key_prefix: str = "drone-rental"
    redis_socket_timeout_seconds: float = 2.0
    redis_connect_timeout_seconds: float = 2.0

    redis_drone_list_cache_ttl_seconds: int = 60
    redis_drone_detail_cache_ttl_seconds: int = 120
    redis_jwt_blacklist_ttl_cap_seconds: int = 86400
    redis_idempotency_ttl_seconds: int = 120
    redis_lock_ttl_seconds: int = 10
    redis_lock_wait_seconds: float = 2.0

    # 自动读取项目目录下的 .env 进行覆盖，即 .env 的优先级高
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 转换 CORS_ORIGINS 中的地址
    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    # 构造最终模型 API 地址
    @property
    def ai_chat_completions_url(self) -> str:
        return self.ai_model_base_url.rstrip("/") + "/chat/completions"

    @property
    def ragflow_dataset_ids(self) -> list[str]:
        return [item.strip() for item in self.ai_ragflow_dataset_ids.split(",") if item.strip()]

    @property
    def mcp_allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.ai_mcp_allowed_hosts.split(",") if item.strip()]

    @property
    def mcp_allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.ai_mcp_allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
