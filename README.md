# PyPolicyd - Debian Package Template

**PyPolicyd** is a high-performance SMTP policy daemon for Postfix that provides advanced rate limiting, recipient controls, and message size restrictions. Built in Python with a focus on simplicity and reliability, it offers hierarchical policy management with domain and user-specific rules.

## Key Features

- 🚀 **Multi-window Rate Limiting** - Flexible time windows (seconds to months)
- 🎯 **Hierarchical Policies** - Domain-wide and user-specific rules
- ⚡ **High Performance** - SQLite backend with automatic cleanup
- 🔧 **Easy Configuration** - Simple YAML configuration files
- 🛡️ **Security Focused** - Dedicated user, proper permissions, input validation
- 📊 **Production Ready** - Comprehensive logging, monitoring, and systemd integration
- 🐧 **Debian Packages** - Ready-to-install .deb packages with automated CI/CD


## Project Structure

```
pypolicyd/
├── debian/                     # Debian configuration files
│   ├── control                # Package metadata
│   ├── changelog              # Package changelog
│   ├── rules                  # Build rules
│   ├── install                # Files to install
│   ├── postinst               # Post-installation script
│   ├── prerm                  # Pre-removal script
│   ├── postrm                 # Post-removal script
│   └── compat                 # Debhelper version
├── src/                       # Python source code
│   └── pypolicyd/
│       ├── __init__.py
│       └── smtp_policy_daemon.py  # Main SMTP Policy Daemon (includes daemon functionality)
├── etc/                       # Configuration files
│   └── pypolicyd/
│       ├── main.yml           # Main configuration
│       └── policy-rules.yml   # SMTP policy rules (users/domains)
├── systemd/                   # Systemd unit files
│   └── pypolicyd.service
├── scripts/                   # Utility scripts
│   └── pypolicyd-ctl
└── setup.py                  # Python setup
```

## Features

- ✅ **SMTP Policy Daemon** for Postfix with advanced rate limiting
- ✅ Automatic `pypolicyd` user/group creation
- ✅ Log directory in `/var/log/pypolicyd/`
- ✅ Configuration files in `/etc/pypolicyd/`
- ✅ Complete systemd integration
- ✅ Daemon control scripts
- ✅ Proper permission management
- ✅ Multi-window rate limiting (e.g., 10/1m, 100/1h, 1000/1d)
- ✅ Hierarchical policies (domain + user)
- ✅ SQLite database for persistence
- ✅ Flexible YAML configuration

## Usage

1. Customize files according to your needs
2. Modify `debian/control` with your package metadata
3. Update `setup.py` with your project information
4. Configure SMTP policies in `etc/pypolicyd/main.yml` and rules in `etc/pypolicyd/policy-rules.yml`
5. Build the package: `dpkg-buildpackage -us -uc`

## SMTP Policy Configuration

The daemon implements a policy system for Postfix with simplified configuration:

### Configuration Files

- **`main.yml`**: Main daemon configuration (logging, database, ports, default policies)
- **`policy-rules.d/`**: Directory with modular policy rules organized by domain (recommended)
- **`policy-rules.yml`**: Single file with all policy rules (legacy compatibility)

## Configuration Reference

### main.yml Parameters

The main configuration file `/etc/pypolicyd/main.yml` contains all daemon settings organized in sections:

#### Daemon Configuration

```yaml
daemon:
  name: "pypolicyd"                              # Service name
  pid_file: "/var/run/pypolicyd/pypolicyd.pid"   # PID file location
  log_file: "/var/log/pypolicyd/pypolicyd.log"   # Main log file
  log_level: "INFO"                              # DEBUG, INFO, WARNING, ERROR
  config_file: "/etc/pypolicyd/main.yml"         # This configuration file
  database: "/var/lib/pypolicyd/policy.db"       # SQLite database path
  host: "127.0.0.1"                              # Listen address
  port: 10040                                    # Listen port (Postfix policy)
  
  # Logging Configuration
  log_level: "INFO"                              # Policy-specific log level
  log_file: "/var/log/pypolicyd/smtp-policy.log" # Policy log file
  log_to_syslog: false                           # Enable syslog logging
  syslog_facility: "mail"                        # Syslog facility (mail, daemon, local0-7)
  log_request: "rejected"                        # Log level: all, rejected, none
  
  # Advanced Settings
  enable_advanced_rates: true                    # Enable multi-window rate tracking
  cleanup_interval: 300                          # Database cleanup interval (seconds)
  
  # Policy Rules Location
  policy_rules_file: "/etc/pypolicyd/policy-rules.d"  # Directory for modular rules
  # OR for single file:
  # policy_rules_file: "/etc/pypolicyd/policy-rules.yml"
```

#### Default Policy Settings

```yaml
default_policy:
  max_recipients: 50        # Default max recipients per email
  max_size: "25M"          # Default max email size (K, M, G suffixes)
  rate_limits:             # Default rate limits (applied when no specific rule)
    - "10/1m"             # 10 emails per minute
    - "100/1h"            # 100 emails per hour  
    - "1000/1d"           # 1000 emails per day
```

#### Monitoring Configuration

```yaml
monitoring:
  enabled: true                                  # Enable performance monitoring
  interval: 60                                  # Monitoring interval (seconds)
  metrics_file: "/var/log/pypolicyd/metrics.log" # Metrics output file
```

### Policy Rules Configuration

#### Directory Structure (Recommended)

Using the modular approach with `/etc/pypolicyd/policy-rules.d/`:

```
/etc/pypolicyd/policy-rules.d/
├── README.md              # Documentation for rule organization
├── company.com.yml        # Rules for company.com domain
├── example.com.yml        # Rules for example.com domain  
└── test.com.yml          # Rules for test.com domain
```

Each file contains domain-specific policies:

**example.com.yml:**
```yaml
domains:
    - name: "example.com"
      # Domain-wide limits (affect all users in domain)
      domain_limits:
        rate_limits: ["1000/1h", "10000/1d"]
        max_recipients: 100
        max_size: "50M"
      
      # Individual user policies
      users:
        "admin@example.com":
          rate_limits: ["100/1h", "1000/1d"]
          max_recipients: 100
          max_size: "50M"
        
        "user@example.com":
          rate_limits: ["50/1h", "500/1d"]
          max_recipients: 50
          max_size: "25M"
        
        # Wildcard for all users in domain
        "*@example.com":
          rate_limits: ["20/1h", "200/1d"]
          max_recipients: 25
          max_size: "10M"
```

#### Rate Limiting Hierarchy

The system enforces hierarchical rate limiting:

1. **Domain-level limits**: Apply to all users in the domain
2. **User-specific limits**: Cannot exceed domain limits
3. **Wildcard rules**: Default for users without specific rules

Example of hierarchical enforcement:

```yaml
smtp_domains:
  "company.com":
    domain_limits:
      rate_limits: ["500/1h"]    # Domain maximum: 500/hour
    users:
      "admin@company.com":
        rate_limits: ["100/1h"]  # User limit: 100/hour (within domain limit)
      "*@company.com":
        rate_limits: ["50/1h"]   # Default for other users: 50/hour
```

#### Rate Limit Formats

Rate limits use the format `count/window`:

- **Time units**: `s` (seconds), `m` (minutes), `h` (hours), `d` (days)
- **Examples**: 
  - `"10/1m"` = 10 emails per minute
  - `"100/1h"` = 100 emails per hour
  - `"1000/1d"` = 1000 emails per day

#### Size Formats

Email size limits support standard suffixes:

- **Units**: `K` (kilobytes), `M` (megabytes), `G` (gigabytes)
- **Examples**: `"10M"`, `"500K"`, `"1G"`

#### Authentication Matching

Policy matching prioritizes SASL authentication:

1. **Primary**: `sasl_username` (authenticated user)
2. **Fallback**: `sender` (envelope sender for compatibility)

This ensures policies are applied to the authenticated user, not just the message sender.

### Legacy Single File Format

For backward compatibility, you can still use a single `/etc/pypolicyd/policy-rules.yml` file:

```yaml
# Domain rules (applied to all users in the domain)
"*@example.com":
  max_recipients: 100
  max_size: "50M"
  rate_limits:
    - "50/1m"        # Max 50 emails per minute
    - "500/1h"       # Max 500 emails per hour
    - "5000/1d"      # Max 5000 emails per day

# User-specific rules (override domain rules)
"admin@example.com":
  max_recipients: 200
  max_size: "100M"
  rate_limits:
    - "1/1s"         # Max 1 email per second
    - "100/5m"       # Max 100 emails per 5 minutes
    - "200/1h"       # Max 200 emails per hour
```

### Features

- **Multi-window Rate Limiting**: Supports seconds (s), minutes (m), hours (h), days (d)
- **Size Limits**: Message size limits (K, M, G)
- **Recipient Limits**: Number of recipients limit per email
- **Policy Hierarchy**: Domain limits enforced, user-specific policies cannot exceed them
- **Modular Configuration**: Organize policies by domain using the `policy-rules.d/` directory
- **SASL Authentication**: Policies applied based on authenticated user (sasl_username)
## Notes

- The daemon will run as `pypolicyd` user
- Logs will be written to `/var/log/pypolicyd/`
- Configurations will be in `/etc/pypolicyd/`
- SQLite database will be in `/var/lib/pypolicyd/`
- The service can be managed with `systemctl start/stop/restart pypolicyd`
- The SMTP daemon listens on port 10040 (configurable)

## Installation and Setup

### 1. Package Build

```bash
# Clone or download the template
cd pypolicyd/

# Verify everything is OK
./test_smtp_daemon.py

# Build the package
./build-package.sh
```

### 2. Installation

```bash
# Install the package
sudo dpkg -i build/policyd_*.deb

# Resolve dependencies if needed
sudo apt-get install -f
```

### 3. Configuration

#### A. Configure SMTP Policies

Edit `/etc/pypolicyd/main.yml`:

```yaml
# Default policy
default_policy:
  rate_limits:
    - "10/1m"    # 10 emails per minute
    - "100/1h"   # 100 emails per hour
    - "1000/1d"  # 1000 emails per day
  max_recipients: 50
  max_size: 25M
```

#### B. Configure Postfix

Add to `/etc/postfix/main.cf`:

```
# Policy service
smtpd_recipient_restrictions = 
    permit_mynetworks,
    permit_sasl_authenticated,
    check_policy_service inet:127.0.0.1:10040,
    reject_unauth_destination
```

### 4. Startup

```bash
# Start the service
sudo systemctl start pypolicyd

# Enable at boot
sudo systemctl enable pypolicyd

# Check status
sudo systemctl status pypolicyd
sudo pypolicyd-ctl status
```

## Service Management

### Control Script `pypolicyd-ctl`

```bash
# Status check
sudo pypolicyd-ctl status

# Start/Stop/Restart
sudo pypolicyd-ctl start
sudo pypolicyd-ctl stop  
sudo pypolicyd-ctl restart

# Reload configuration
sudo pypolicyd-ctl reload

# View logs
sudo pypolicyd-ctl logs 100
sudo pypolicyd-ctl follow-logs

# Test configuration
sudo pypolicyd-ctl test-config

# Complete information
sudo pypolicyd-ctl info
```

### Systemd Commands

```bash
# Standard management
sudo systemctl start/stop/restart/reload pypolicyd
sudo systemctl status pypolicyd
sudo journalctl -u pypolicyd -f

# Enable/disable
sudo systemctl enable/disable pypolicyd
```

## Advanced Configuration

### Rate Limiting

The system supports multi-window rate limiting with flexible syntax:

```yaml
rate_limits:
  - "10/1m"     # 10 emails per minute
  - "100/1h"    # 100 emails per hour  
  - "500/4h"    # 500 emails every 4 hours
  - "1000/1d"   # 1000 emails per day
  - "5000/1M"   # 5000 emails per month
```

**Supported units:**
- `s` = seconds
- `m` = minutes  
- `h` = hours
- `d` = days
- `M` = months (30 days)

### Hierarchical Policies

Policies follow a **domain → user** hierarchy:

1. **Domain Policy**: Maximum limits for the entire domain
2. **User Policy**: Cannot exceed domain limits
3. **Automatic Validation**: The system prevents invalid configurations

### Logging

Logging configuration in `main.yml`:

```yaml
daemon_config:
  log_level: INFO              # DEBUG, INFO, WARNING, ERROR
  log_file: /var/log/pypolicyd/smtp-policy.log
  log_to_syslog: false        # true for syslog
  syslog_facility: mail       # mail, daemon, local0-7
  log_request: rejected       # all, rejected, none
```

## Troubleshooting

### Common Issues

#### 1. Service won't start

```bash
# Check logs
sudo journalctl -u pypolicyd -n 50

# Verify configuration
sudo pypolicyd-ctl test-config

# Test manually
sudo -u pypolicyd /usr/bin/pypolicyd --foreground
```

#### 2. Policies not working

```bash
# Verify Postfix connection
telnet 127.0.0.1 10040

# Check request logs
sudo tail -f /var/log/pypolicyd/smtp-policy.log

# Test YAML configuration
python3 -c "import yaml; yaml.safe_load(open('/etc/pypolicyd/main.yml'))"
```

#### 3. Rate limiting not working

```bash
# Verify database
sudo ls -la /var/lib/pypolicyd/
sudo sqlite3 /var/lib/pypolicyd/policy.db "SELECT * FROM rate_limits;"

# Enable full logging
# In main.yml: log_request: all
sudo pypolicyd-ctl reload
```

### Important Files

- **Configuration**: `/etc/pypolicyd/main.yml`
- **Log**: `/var/log/pypolicyd/pypolicyd.log`
- **Database**: `/var/lib/pypolicyd/policy.db`
- **PID**: `/var/run/pypolicyd/pypolicyd.pid`
- **Service**: `/lib/systemd/system/pypolicyd.service`

## Customization

### Modifying the Template

1. **Listen port**: Modify `port` in `/etc/pypolicyd/main.yml`
2. **Database**: Change `database` in configuration
3. **Logging**: Customize in `daemon_config` of YAML
4. **Policies**: Add domains and users in `smtp_domains`

### Extending Functionality

The template is modular and can be extended:

- Add new checks in `smtp_policy_daemon.py`
- Modify policies in `PolicyConfig`
- Extend rate tracking in `MultiWindowRateTracker`

## Performance

The daemon is optimized for performance:

- **SQLite Database**: Fast atomic operations
- **Automatic Cleanup**: Removes old data periodically
- **Memory Efficient**: Optimized memory management
- **Async I/O**: Asynchronous connection handling

### Monitoring

```bash
# Database statistics
sudo sqlite3 /var/lib/pypolicyd/policy.db "
SELECT 
    substr(key, 1, 20) as key_prefix,
    count(*) as entries,
    avg(count) as avg_count
FROM rate_limits 
GROUP BY substr(key, 1, 20);"

# Performance logs
sudo grep "rate check" /var/log/pypolicyd/smtp-policy.log | tail -20
```

## Security

- ✅ Execution with dedicated `pypolicyd` user
- ✅ Configuration file permissions: `640` (root:pypolicyd)
- ✅ Protected directories: `/var/lib/pypolicyd`, `/var/log/pypolicyd`
- ✅ Active systemd security features
- ✅ Configuration input validation
- ✅ Safe error handling

## Support

For issues or improvements:

1. Check logs: `sudo pypolicyd-ctl logs`
2. Verify configuration: `sudo pypolicyd-ctl test-config`
3. Test functionality: `./test_smtp_daemon.py`
4. Debug mode: Start with `--foreground`

The template is designed to be robust, secure, and easily maintainable in production.
