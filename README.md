# Drone-Rental
一个无人机租赁系统的全栈开发记录

目前已实现：用户租赁、资质审核、空域备案、支付宝支付接口、物流状态、归还评价、故障报修、维修工单、实时通知、 AI 智能助手…… 

更多功能边学习边添加。 😜

# 技术栈
前端：Vue 3、Vite 5、Element Plus、Echarts

后端：Python 3.11、FastAPI 0.116、Uvicorn REST API、OpenAPI、SSE 和 WebSocket。

数据库：MySQL

AI 模型接口：deepseek-v4-flash

支持支付接口：alipay

安全技术：JWT、BCrypt、CORS、限流……

# 目标
项目业务原型参考开源仓库：[Drone-Rental-System](https://github.com/springmeng/Drone-Rental-System)

⚠️ 重要说明：原型采用Java开发，本项目基于Python独立重构实现，未复用原项目源代码，仅借鉴无人机租赁业务流程与系统需求设计思路。

项目目标：
1. 梳理并优化租赁、归还、运维、结算等无人机租赁完整业务闭环，修复原型缺陷，完善系统功能；
2. 集成智能体系统，赋能智能客服、订单智能分配、设备状态监控、风险预警、自动化工单流转；
3. 开展架构优化、系统安全与生产环境适配工作，实现一套支持商业化部署的智能化无人机租赁解决方案。
