# Exchanges
CONFIG_EXCHANGE = 'config'
RAW_DATA_EXCHANGE = 'raw_data'
STORE_EXCHANGE = 'store'
ALERT_EXCHANGE = 'alert'
HEALTH_CHECK_EXCHANGE = 'health_check'

# Queues
CONFIGS_MANAGER_HEARTBEAT_QUEUE = "configs_manager_heartbeat_queue"
GH_MON_MAN_HEARTBEAT_QUEUE_NAME = 'github_monitors_manager_heartbeat_queue'
GH_MON_MAN_CONFIGS_QUEUE_NAME = 'github_monitors_manager_configs_queue'
SYS_MON_MAN_HEARTBEAT_QUEUE_NAME = 'system_monitors_manager_heartbeat_queue'
SYS_MON_MAN_CONFIGS_QUEUE_NAME = 'system_monitors_manager_configs_queue'
NODE_MON_MAN_CONFIGS_QUEUE_NAME = 'node_monitors_manager_configs_queue'
NODE_MON_MAN_HEARTBEAT_QUEUE_NAME = 'node_monitors_manager_heartbeat_queue'
GITHUB_DT_INPUT_QUEUE_NAME = 'github_data_transformer_input_queue'
SYSTEM_DT_INPUT_QUEUE_NAME = 'system_data_transformer_input_queue'
DT_MAN_HEARTBEAT_QUEUE_NAME = 'data_transformers_manager_heartbeat_queue'
SYS_ALERTER_INPUT_QUEUE_NAME_TEMPLATE = "system_alerter_input_queue_{}"
GITHUB_ALERTER_INPUT_QUEUE_NAME = 'github_alerter_input_queue'
SYS_ALERTERS_MAN_HEARTBEAT_QUEUE_NAME = \
    'system_alerters_manager_heartbeat_queue'
SYS_ALERTERS_MANAGER_CONFIGS_QUEUE_NAME = \
    'system_alerters_manager_configs_queue'
GH_ALERTERS_MAN_HEARTBEAT_QUEUE_NAME = 'github_alerters_manager_heartbeat_queue'
ALERT_ROUTER_CONFIGS_QUEUE_NAME = 'alert_router_configs_queue'
ALERT_ROUTER_INPUT_QUEUE_NAME = 'alert_router_input_queue'
ALERT_ROUTER_HEARTBEAT_QUEUE_NAME = 'alert_router_heartbeat_queue'
ALERT_STORE_INPUT_QUEUE_NAME = 'alert_store_input_queue'
CONFIGS_STORE_INPUT_QUEUE_NAME = 'configs_store_input_queue'
GITHUB_STORE_INPUT_QUEUE_NAME = 'github_store_input_queue'
SYSTEM_STORE_INPUT_QUEUE_NAME = 'system_store_input_queue'
DATA_STORES_MAN_HEARTBEAT_QUEUE_NAME = 'data_stores_manager_heartbeat_queue'
CHAN_ALERTS_HAN_INPUT_QUEUE_NAME_TEMPLATE = '{}_alerts_handler_input_queue'
CHAN_CMDS_HAN_HB_QUEUE_NAME_TEMPLATE = '{}_commands_handler_heartbeat_queue'
CHANNELS_MANAGER_CONFIGS_QUEUE_NAME = 'channels_manager_configs_queue'
CHANNELS_MANAGER_HEARTBEAT_QUEUE_NAME = 'channels_manager_heartbeat_queue'
HB_HANDLER_HEARTBEAT_QUEUE_NAME = 'heartbeat_handler_heartbeat_queue'

# Routing Keys
SYSTEM_RAW_DATA_ROUTING_KEY = 'system'
CHAINLINK_NODE_RAW_DATA_ROUTING_KEY = 'node.chainlink'
GITHUB_RAW_DATA_ROUTING_KEY = 'github'
GH_MON_MAN_CONFIGS_ROUTING_KEY_CHAINS = 'chains.*.*.repos_config'
GH_MON_MAN_CONFIGS_ROUTING_KEY_GEN = 'general.repos_config'
SYS_MON_MAN_CONFIGS_ROUTING_KEY_CHAINS_SYS = 'chains.*.*.systems_config'
SYS_MON_MAN_CONFIGS_ROUTING_KEY_CHAINS_NODES = 'chains.*.*.nodes_config'
SYS_MON_MAN_CONFIGS_ROUTING_KEY_GEN = 'general.systems_config'
NODE_MON_MAN_CONFIGS_ROUTING_KEY_CHAINS = 'chains.*.*.nodes_config'
GITHUB_TRANSFORMED_DATA_ROUTING_KEY = 'transformed_data.github'
SYSTEM_TRANSFORMED_DATA_ROUTING_KEY_TEMPLATE = 'transformed_data.system.{}'
SYSTEM_ALERT_ROUTING_KEY = 'alert.system'
GITHUB_ALERT_ROUTING_KEY = 'alert.github'
SYS_ALERTERS_MAN_CONFIGS_ROUTING_KEY_CHAIN = 'chains.*.*.alerts_config'
SYS_ALERTERS_MAN_CONFIGS_ROUTING_KEY_GEN = 'general.alerts_config'
ALERT_ROUTER_CONFIGS_ROUTING_KEY = 'channels.*'
ALERT_ROUTER_INPUT_ROUTING_KEY = 'alert.*'
ALERT_STORE_INPUT_ROUTING_KEY = 'alert'
CONFIGS_STORE_INPUT_ROUTING_KEY = '#'
SYSTEM_STORE_INPUT_ROUTING_KEY = 'transformed_data.system.*'
CHANNEL_HANDLER_INPUT_ROUTING_KEY_TEMPLATE = 'channel.{}'
CONSOLE_HANDLER_INPUT_ROUTING_KEY = "channel.console"
LOG_HANDLER_INPUT_ROUTING_KEY = 'channel.log'
CHANNELS_MANAGER_CONFIGS_ROUTING_KEY = 'channels.*'
PING_ROUTING_KEY = 'ping'
HEARTBEAT_INPUT_ROUTING_KEY = 'heartbeat.*'
HEARTBEAT_OUTPUT_WORKER_ROUTING_KEY = 'heartbeat.worker'
HEARTBEAT_OUTPUT_MANAGER_ROUTING_KEY = 'heartbeat.manager'

# Sleep periods
RESTART_SLEEPING_PERIOD = 10
RE_INITIALISE_SLEEPING_PERIOD = 10

# Templates
EMAIL_HTML_TEMPLATE = """<style type="text/css">
.email {{font-family: sans-serif}}
.tg  {{border:none; border-spacing:0;border-collapse: collapse;}}
.tg td{{border-style:none;border-width:0px;overflow:hidden; padding:10px 5px;word-break:normal;}}
.tg th{{border-style:none;border-width:0px;overflow:hidden;padding:10px 5px;word-break:normal;text-align:left;background-color:lightgray;}}
@media screen and (max-width: 767px) {{.tg {{width: auto !important;}}.tg col {{width: auto !important;}}.tg-wrap {{overflow-x: auto;-webkit-overflow-scrolling: touch;}} }}</style>
<div class="email">
<h2>PANIC Alert</h2>
<p>An alert was generated with the following details:</p>
<div class="tg-wrap"><table class="tg">
<tbody>
  <tr>
    <th>Alert Code:</th>
    <td>{alert_code}</td>
  </tr>
  <tr>
    <th>Severity:</th>
    <td>{severity}</td>
  </tr>
  <tr>
    <th>Message:</th>
    <td>{message}</td>
  </tr>
  <tr>
    <th>Triggered At:</th>
    <td>{date_time}</td>
  </tr>
  <tr>
    <th>Parent ID:</th>
    <td>{parent_id}</td>
  </tr>
  <tr>
    <th>Origin ID:</th>
    <td>{origin_id}</td>
  </tr>
</tbody>
</table></div>
</div>"""

EMAIL_TEXT_TEMPLATE = """
PANIC Alert!
======================
An alert was generated with the following details:

Alert Code: {alert_code}
Severity: {severity}
Message: {message}
Triggered At: {date_time}
Parent ID: {parent_id}
Origin ID: {origin_id}
"""

# Component names/name templates/ids
GITHUB_ALERTER_NAME = 'GitHub Alerter'
SYSTEM_STORE_NAME = 'System Store'
CONFIG_STORE_NAME = 'Config Store'
GITHUB_STORE_NAME = 'GitHub Store'
ALERT_STORE_NAME = 'Alert Store'
SYSTEM_DATA_TRANSFORMER_NAME = 'System Data Transformer'
GITHUB_DATA_TRANSFORMER_NAME = 'GitHub Data Transformer'
SYSTEM_MONITORS_MANAGER_NAME = 'System Monitors Manager'
GITHUB_MONITORS_MANAGER_NAME = 'GitHub Monitors Manager'
NODE_MONITORS_MANAGER_NAME = 'Node Monitors Manager'
DATA_TRANSFORMERS_MANAGER_NAME = 'Data Transformers Manager'
SYSTEM_ALERTERS_MANAGER_NAME = 'System Alerters Manager'
GITHUB_ALERTER_MANAGER_NAME = 'GitHub Alerter Manager'
DATA_STORE_MANAGER_NAME = 'Data Store Manager'
ALERT_ROUTER_NAME = 'Alert Router'
CONFIGS_MANAGER_NAME = 'Configs Manager'
CHANNELS_MANAGER_NAME = 'Channels Manager'
HEARTBEAT_HANDLER_NAME = 'Heartbeat Handler'
PING_PUBLISHER_NAME = 'Ping Publisher'
HEALTH_CHECKER_MANAGER_NAME = 'Health Checker Manager'
CONSOLE_CHANNEL_NAME = 'CONSOLE'
CONSOLE_CHANNEL_ID = 'CONSOLE'
LOG_CHANNEL_NAME = 'LOG'
TELEGRAM_COMMAND_HANDLERS_NAME = 'Telegram Command Handlers'
LOG_CHANNEL_ID = 'LOG'
SYSTEM_ALERTER_NAME_TEMPLATE = 'System alerter ({})'
GITHUB_MONITOR_NAME_TEMPLATE = 'GitHub monitor ({})'
SYSTEM_MONITOR_NAME_TEMPLATE = 'System monitor ({})'
NODE_MONITOR_NAME_TEMPLATE = 'Node monitor ({})'
TELEGRAM_ALERTS_HANDLER_NAME_TEMPLATE = 'Telegram Alerts Handler ({})'
TELEGRAM_COMMANDS_HANDLER_NAME_TEMPLATE = 'Telegram Commands Handler ({})'
TWILIO_ALERTS_HANDLER_NAME_TEMPLATE = 'Twilio Alerts Handler ({})'
PAGERDUTY_ALERTS_HANDLER_NAME_TEMPLATE = 'PagerDuty Alerts Handler ({})'
EMAIL_ALERTS_HANDLER_NAME_TEMPLATE = 'Email Alerts Handler ({})'
OPSGENIE_ALERTS_HANDLER_NAME_TEMPLATE = 'Opsgenie Alerts Handler ({})'
CONSOLE_ALERTS_HANDLER_NAME_TEMPLATE = 'Console Alerts Handler ({})'
LOG_ALERTS_HANDLER_NAME_TEMPLATE = 'Log Alerts Handler ({})'

# CONFIG Folder Identifiers
GENERAL = 'general'
CHAINS = 'chains'
CHANNELS = 'channels'
GLOBAL = 'global'
COSMOS_NODE_CONFIG = 'cosmos_nodes_config'
SUBSTRATE_NODE_CONFIG = 'substrate_nodes_config'
NODES_CONFIG = 'nodes_config'
REPOS_CONFIG = 'repos_config'
SYSTEMS_CONFIG = 'systems_config'
ALERTS_CONFIG = 'alerts_config'
TELEGRAM_CONFIG = 'telegram_config'
EMAIL_CONFIG = 'email_config'
OPSGENIE_CONFIG = 'opsgenie_config'
PAGERDUTY_CONFIG = 'pagerduty_config'
TWILIO_CONFIG = 'twilio_config'

# Helpers to assist with routing key parsing
"""
This configuration object is useful as when COSMOS and SUBSTRATE nodes
are added, they will have multiple monitorable sources and not just
systems, therefore by storing them in a list and iterating through
the dictionaries it is easier to bundle up the list of monitorable
data.
"""
MONITORABLES_PARSING_HELPER = {
    REPOS_CONFIG: [{
        "id": 'id',
        "name_key": 'repo_name',
        "monitor_key": 'monitor_repo',
        "config_key": 'repos'
    }],
    SYSTEMS_CONFIG: [{
        "id": 'id',
        "name_key": 'name',
        "monitor_key": 'monitor_system',
        "config_key": 'systems'
    }],
    COSMOS_NODE_CONFIG: [{
        "id": 'id',
        "name_key": 'name',
        "monitor_key": 'monitor_system',
        "config_key": 'systems'
    }],
    SUBSTRATE_NODE_CONFIG: [{
        "id": 'id',
        "name_key": 'name',
        "monitor_key": 'monitor_system',
        "config_key": 'systems'
    }]
}
