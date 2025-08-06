# Eway充电桩 Home Assistant 集成

一个功能完整的Home Assistant自定义集成，用于监控和控制Eway充电桩设备。

## 目录

- [功能特性](#功能特性)
- [安装方法](#安装方法)
- [配置方式](#配置方式)
- [传感器说明](#传感器说明)
- [控制功能](#控制功能)
- [响应处理](#响应处理)
- [使用指南](#使用指南)
- [测试说明](#测试说明)
- [故障排除](#故障排除)
- [开发说明](#开发说明)

## 功能特性

### 核心功能
- **自动设备发现**: 通过mDNS自动发现网络中的Eway充电桩
- **实时状态监控**: 监控充电状态、电流、连接状态等
- **远程控制**: 支持充电开关、电流调节、密码重置等控制功能
- **NFC管理**: 支持NFC卡片的添加、删除和状态管理
- **多语言支持**: 完整的中英文界面支持
- **可配置传感器**: 用户可选择启用或禁用特定传感器

### 支持的设备类型
- Eway CS-TFT 系列充电桩
- 支持WebSocket通信的Eway设备
- 支持MQTT协议的充电桩设备

## 安装方法

### 方法一：通过HACS安装（推荐）

1. 确保已安装HACS
2. 在HACS中添加自定义存储库
3. 搜索"Eway Charger"并安装
4. 重启Home Assistant

### 方法二：手动安装

1. 下载最新版本的集成文件
2. 将`eway_charger`文件夹复制到`custom_components`目录
3. 重启Home Assistant
4. 在集成页面添加"Eway Charger"

## 配置方式

### 自动发现配置

1. 进入"配置" > "设备与服务"
2. 点击"添加集成"
3. 搜索"Eway Charger"
4. 选择"自动发现"
5. 系统将扫描网络中的设备
6. 选择您的充电桩并完成配置

### 手动配置

1. 选择"手动配置"
2. 输入以下信息：
   - **主机地址**: 充电桩IP地址
   - **端口**: WebSocket端口（默认8080）
   - **设备ID**: 充电桩设备ID
   - **设备序列号**: 充电桩序列号

### 传感器配置

配置完成后可自定义传感器：
1. 在集成页面点击"配置"
2. 选择需要的传感器
3. 设置扫描间隔（推荐30-60秒）
4. 保存配置

## 传感器说明

### 设备信息传感器

| 传感器ID | 中文名称 | 英文名称 | 描述 |
|----------|----------|----------|------|
| `app_firmware_version` | 应用固件版本 | App Firmware Version | 应用固件版本信息 |
| `charge_current` | 充电电流 | Charge Current | 当前充电电流值 |
| `charge_status` | 充电状态 | Charge Status | 充电桩工作状态 |
| `gun_status` | 充电枪状态 | Gun Status | 充电枪连接状态 |
| `pile_status` | 充电桩状态 | Pile Status | 设备整体运行状态 |
| `mcb_firmware_version` | MCB固件版本 | MCB Firmware Version | MCB控制板固件版本 |
| `net_firmware_version` | 网络固件版本 | Net Firmware Version | 网络模块固件版本 |
| `net_source` | 网络来源 | Net Source | 网络连接方式 |
| `wifi_ssid` | WiFi SSID | WiFi SSID | 当前连接的WiFi名称 |
| `work_charge_time` | 总充电时长 | Work Charge Time | 累计充电时间 |
| `work_this_time` | 本次充电时长 | Work This Time | 当前会话充电时间 |
| `work_total_time` | 总工作时长 | Work Total Time | 设备总运行时间 |
| `gun_lock` | 充电枪锁状态 | Gun Lock | 充电枪锁定状态 |
| `time_zone` | 时区 | Time Zone | 设备时区设置 |

### 二进制传感器

| 传感器ID | 中文名称 | 英文名称 | 描述 |
|----------|----------|----------|------|
| `charging` | 充电中 | Charging | 是否正在充电 |
| `gun_connected` | 充电枪连接 | Gun Connected | 充电枪是否已连接 |
| `gun_locked` | 充电枪锁定 | Gun Locked | 充电枪是否已锁定 |
| `nfc_enabled` | NFC启用 | NFC Enabled | NFC功能是否启用 |
| `connection` | 连接状态 | Connection | 设备网络连接状态 |
| `error` | 错误状态 | Error | 是否存在错误 |

### 响应传感器

| 传感器ID | 中文名称 | 英文名称 | 描述 |
|----------|----------|----------|------|
| `charging_control_response` | 充电控制响应 | Charging Control Response | 充电开关控制响应 |
| `device_error_response` | 设备错误响应 | Device Error Response | 设备错误状态响应 |
| `device_status_responses` | 设备状态响应 | Device Status Responses | 设备状态查询响应 |

## 控制功能

### 充电控制

#### 充电开关控制
- **实体类型**: Switch（开关）
- **功能**: 启动/停止充电
- **协议**: 通过`/function/get`主题发送控制指令

**使用方法**:
1. 在Home Assistant中找到"充电开关"实体
2. 点击开关控制充电启停
3. 系统会自动发送相应的MQTT指令

## 响应处理

### 充电控制响应
当执行充电控制操作后，设备会返回响应消息，包含以下信息：
- 操作结果（成功/失败）
- 当前充电状态
- 响应时间戳
- 详细的状态信息

### 设备状态响应
设备状态查询的响应包含：
- 充电枪状态（gun-status）
- 充电状态（charge-status）
- 充电桩状态（pile-status）
- 详细的状态值和描述

### 错误响应处理
当设备出现错误时，会返回错误响应：
- 错误代码
- 错误描述
- 错误发生时间
- 错误级别（警告/错误/严重）

## 使用指南

### 仪表板配置示例

#### 基础监控卡片
```yaml
type: entities
title: Eway充电桩状态
entities:
  - sensor.eway_charger_charge_status
  - binary_sensor.eway_charger_charging
  - binary_sensor.eway_charger_gun_connected
  - sensor.eway_charger_charge_current
```

#### 控制面板卡片
```yaml
type: entities
title: 充电控制
entities:
  - switch.eway_charger_charging_switch
```

#### 设备信息卡片
```yaml
type: entities
title: 设备信息
entities:
  - sensor.eway_charger_app_firmware_version
  - sensor.eway_charger_mcb_firmware_version
  - sensor.eway_charger_net_firmware_version
  - sensor.eway_charger_wifi_ssid
```

### 自动化示例

#### 充电完成通知
```yaml
alias: "充电完成通知"
trigger:
  - platform: state
    entity_id: sensor.eway_charger_charge_status
    to: "充电完成"
action:
  - service: notify.mobile_app
    data:
      message: "充电桩充电已完成"
      title: "充电通知"
```

#### 错误状态监控
```yaml
alias: "充电桩错误监控"
trigger:
  - platform: state
    entity_id: binary_sensor.eway_charger_error
    to: "on"
action:
  - service: notify.mobile_app
    data:
      message: "充电桩出现错误，请检查设备状态"
      title: "设备警告"
```

## 测试说明

### 测试环境要求
- Python 3.8 或更高版本
- 与Eway设备在同一局域网内
- 安装必要的依赖包：`pip install zeroconf websockets`

### 独立测试脚本

#### 完整功能测试
```bash
# 使用默认设置（10秒发现超时）
python test_standalone.py

# 自定义发现超时时间（15秒）
python test_standalone.py 15
```

#### 设备发现专用测试
```bash
# 使用默认设置
python test_discovery_only.py

# 自定义超时时间和设备前缀
python test_discovery_only.py 20 EwayCS-TFT
```

### 功能测试

#### NFC卡片响应测试
```bash
python test_nfc_card_responses.py
```

测试内容包括：
- NFC卡片添加响应处理
- NFC卡片删除响应处理
- 无响应数据的情况处理
- 多张卡片操作测试

## 故障排除

### 常见问题

#### 设备发现失败
1. **检查网络连接**: 确保Home Assistant与充电桩在同一局域网
2. **检查防火墙**: 确保mDNS端口（5353）未被阻止
3. **检查设备状态**: 确保充电桩已开机并连接到网络
4. **手动配置**: 如果自动发现失败，尝试手动配置

#### WebSocket连接失败
1. **检查端口**: 确认WebSocket端口（通常8080）是否正确
2. **检查设备ID**: 验证设备ID和序列号是否正确
3. **网络延迟**: 增加连接超时时间
4. **重启设备**: 尝试重启充电桩设备

#### 传感器数据异常
1. **检查扫描间隔**: 避免设置过短的扫描间隔
2. **查看日志**: 检查Home Assistant日志中的错误信息
3. **重新配置**: 尝试删除并重新添加集成
4. **固件版本**: 确认充电桩固件版本兼容

#### 控制指令无响应
1. **检查权限**: 确认设备允许远程控制
2. **网络状态**: 检查设备网络连接状态
3. **指令格式**: 验证发送的指令格式是否正确
4. **设备模式**: 确认设备处于可控制状态

### 日志调试

在`configuration.yaml`中启用调试日志：
```yaml
logger:
  default: info
  logs:
    custom_components.eway_charger: debug
```

### 网络诊断

#### 检查mDNS服务
```bash
# macOS/Linux
avahi-browse -rt _http._tcp

# Windows
dns-sd -B _http._tcp
```

#### 检查WebSocket连接
```bash
# 使用curl测试WebSocket
curl -i -N -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Key: test" \
     -H "Sec-WebSocket-Version: 13" \
     http://[设备IP]:8080/
```

## 开发说明

### 项目结构
```
eway_charger/
├── __init__.py              # 集成初始化
├── config_flow.py           # 配置流程
├── const.py                 # 常量定义
├── coordinator.py           # 数据协调器
├── device_discovery.py      # 设备发现
├── sensor.py               # 传感器实体
├── binary_sensor.py        # 二进制传感器
├── switch.py               # 开关实体
├── websocket_client.py     # WebSocket客户端
├── translations/           # 多语言翻译
│   ├── en.json
│   └── zh.json
└── manifest.json           # 集成清单
```

### 协议说明

#### MQTT主题格式
- **属性获取**: `/设备ID/设备SN/property/get`
- **属性响应**: `/设备ID/设备SN/property/post`
- **功能控制**: `/设备ID/设备SN/function/get`
- **功能响应**: `/设备ID/设备SN/function/post`

#### WebSocket消息格式
```json
{
  "topic": "/device_id/device_sn/property/get",
  "payload": {
    "id": "command_id",
    "value": "command_value",
    "remark": "command_remark",
    "userId": ""
  }
}
```

### 扩展开发

#### 添加新传感器
1. 在`const.py`中定义传感器配置
2. 在`sensor.py`中实现传感器类
3. 在翻译文件中添加多语言支持
4. 更新文档说明

#### 添加新控制功能
1. 选择合适的实体类型（switch/number/text等）
2. 实现控制逻辑和协议格式
3. 添加响应处理逻辑
4. 编写测试用例

### 版本历史

#### v1.0.0
- 初始版本发布
- 基础设备发现和连接功能
- 核心传感器支持

#### v1.1.0
- 新增充电控制功能
- 新增电流调节功能
- 改进错误处理

#### v1.2.0
- 新增NFC管理功能
- 新增密码重置功能
- 新增网络模式控制

#### v1.3.0
- 新增响应传感器系统
- 改进数据处理逻辑
- 增强错误诊断功能

#### v1.4.0
- 新增NFC卡片管理响应
- 完善设备状态响应处理
- 优化用户界面体验

## 许可证

本项目采用MIT许可证，详见LICENSE文件。

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 支持

如果您在使用过程中遇到问题，请：
1. 查看本文档的故障排除部分
2. 检查GitHub Issues中的已知问题
3. 提交新的Issue描述您的问题

---

**注意**: 本集成仅适用于支持相应协议的Eway充电桩设备。使用前请确认您的设备型号和固件版本的兼容性。