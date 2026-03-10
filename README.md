# Bosch SmartLife for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for the **Bosch SmartLife** smart home platform (China market, based on AbleCloud IoT).

Control your Bosch smart panel and connected sub-devices directly from Home Assistant.

## Supported Devices

| Type | HA Platform | Features |
|------|-------------|----------|
| Lights | `light` | On/Off, Brightness |
| Air Conditioners | `climate` | Power, Mode (Cool/Heat/Dry/Fan/Auto), Temperature, Fan Speed |
| Curtains | `cover` | Open/Close/Stop (dual-channel: curtain + sheer) |

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** > **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Search for "Bosch SmartLife" and install
5. Restart Home Assistant

### Manual

1. Download this repository
2. Copy the contents to `custom_components/bosch_smartlife/` in your HA config directory
3. Restart Home Assistant

## Configuration

### UI Setup (Recommended)

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **Bosch SmartLife**
3. Enter your phone number and password
4. If multiple panels are found, select the one to configure

### YAML Setup (Legacy)

Add to your `configuration.yaml`:

```yaml
bosch_smartlife:
  account: "your_phone_number"
  password: "your_password"
  panel_id: "your_panel_id"
```

## API Details

This integration communicates with the Bosch SmartLife cloud service built on the **AbleCloud** IoT platform.

- **Endpoint**: `https://api.bosch-smartlife.com`
- **Auth**: SHA-1 signed headers with token-based authentication
- **Polling**: Device states are polled every 30 seconds
- **Protocol**: REST API with JSON payloads and custom `X-Zc-*` signature headers

### Authentication Flow

1. Login with phone number + password to obtain a token
2. Subsequent requests are signed with: `SHA1(timeout + timestamp + nonce + token)`
3. Token auto-refreshes on expiry (error code 1999)

## Troubleshooting

- **"No panels found"**: Ensure your account has at least one panel bound in the Bosch SmartLife app
- **Devices not showing**: Only sub-devices connected to the selected panel will appear
- **Connection errors**: Check your network can reach `api.bosch-smartlife.com`

## Credits

- Built for the Bosch SmartLife platform (China) using the AbleCloud IoT API
- Home Assistant community

## License

MIT

---

# 博世智慧生活 Home Assistant 集成

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

适用于 **博世智慧生活** 智能家居平台（中国市场，基于 AbleCloud 物联网平台）的 Home Assistant 自定义集成。

通过 Home Assistant 直接控制博世智能面板及其连接的子设备。

## 支持的设备

| 类型 | HA 平台 | 功能 |
|------|---------|------|
| 灯光 | `light` | 开关、亮度调节 |
| 空调 | `climate` | 电源、模式（制冷/制热/除湿/送风/自动）、温度、风速 |
| 窗帘 | `cover` | 开/关/停（双通道：布帘 + 窗纱） |

## 安装

### HACS（推荐）

1. 在 Home Assistant 中打开 HACS
2. 进入 **集成** > **自定义仓库**
3. 添加本仓库地址，类别选择 **Integration**
4. 搜索 "Bosch SmartLife" 并安装
5. 重启 Home Assistant

### 手动安装

1. 下载本仓库
2. 将文件复制到 HA 配置目录下的 `custom_components/bosch_smartlife/`
3. 重启 Home Assistant

## 配置

### UI 配置（推荐）

1. 进入 **设置** > **设备与服务** > **添加集成**
2. 搜索 **Bosch SmartLife**
3. 输入手机号和密码
4. 如果发现多个面板，选择要配置的面板

### YAML 配置（传统方式）

在 `configuration.yaml` 中添加：

```yaml
bosch_smartlife:
  account: "你的手机号"
  password: "你的密码"
  panel_id: "你的面板ID"
```

## API 说明

本集成通过博世智慧生活云服务（基于 **AbleCloud** 物联网平台）进行通信。

- **接口地址**: `https://api.bosch-smartlife.com`
- **认证方式**: 基于 SHA-1 签名的请求头 + Token 认证
- **轮询间隔**: 每 30 秒更新设备状态
- **协议**: REST API，JSON 数据格式，使用自定义 `X-Zc-*` 签名请求头

## 常见问题

- **"未找到面板"**：请确保你的账号在博世智慧生活 App 中已绑定至少一个面板
- **设备不显示**：只有连接到所选面板的子设备才会出现
- **连接错误**：请检查网络是否能访问 `api.bosch-smartlife.com`

## 许可证

MIT
