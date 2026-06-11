# FT-Bot Production Security Checklist

Complete security checklist for production deployment.

## Pre-Deployment Security

### Server Security
- [ ] Server OS updated to latest version
- [ ] SSH configured with key-based authentication only
- [ ] SSH password authentication disabled
- [ ] SSH root login disabled
- [ ] Non-standard SSH port configured (optional)
- [ ] Fail2Ban installed and configured
- [ ] UFW firewall enabled with minimal rules
- [ ] Automatic security updates enabled
- [ ] Minimal services running (disable unnecessary services)

### User & Permissions
- [ ] Dedicated `ftbot` system user created
- [ ] Application files owned by `ftbot:ftbot`
- [ ] Sensitive files have restrictive permissions (600)
- [ ] No direct root access to application
- [ ] Docker group membership configured for ftbot user

## Application Security

### Backend API
- [ ] `FT_JWT_SECRET` is strong (32+ random characters)
- [ ] `FT_JWT_SECRET` stored securely in environment file
- [ ] Environment file permissions set to 600
- [ ] API rate limiting configured in Nginx
- [ ] CORS properly configured (not using `allow_origins=["*"]` in production)
- [ ] API documentation endpoints disabled or protected
- [ ] Input validation enabled for all endpoints
- [ ] SQL injection protection (using SQLAlchemy ORM)
- [ ] Authentication required for all sensitive endpoints

### Frontend
- [ ] Production build created (not dev build)
- [ ] Source maps removed or protected
- [ ] Environment variables properly configured
- [ ] No sensitive data in client-side code
- [ ] Content Security Policy headers configured

### Database
- [ ] Database file has restricted permissions (600)
- [ ] Database stored outside web root
- [ ] Regular backups configured
- [ ] Backup files encrypted or stored securely
- [ ] Database connection using local socket (not network)

## Network Security

### SSL/TLS
- [ ] Valid SSL certificate installed (Let's Encrypt)
- [ ] HTTP redirects to HTTPS
- [ ] TLS 1.2+ only (TLS 1.0/1.1 disabled)
- [ ] Strong cipher suites configured
- [ ] HSTS header enabled
- [ ] SSL certificate auto-renewal configured
- [ ] OCSP stapling enabled

### Nginx Configuration
- [ ] Security headers configured:
  - [ ] Strict-Transport-Security
  - [ ] X-Frame-Options
  - [ ] X-Content-Type-Options
  - [ ] X-XSS-Protection
  - [ ] Referrer-Policy
  - [ ] Content-Security-Policy
- [ ] Rate limiting configured
- [ ] Request size limits configured
- [ ] Timeout values properly set
- [ ] Access to sensitive paths blocked
- [ ] Server tokens hidden
- [ ] Directory listing disabled

### Firewall Rules
- [ ] Only required ports open (22, 80, 443)
- [ ] Default deny incoming policy
- [ ] Default allow outgoing policy
- [ ] UFW logging enabled
- [ ] Fail2Ban monitoring SSH and Nginx

## Docker Security

### Docker Daemon
- [ ] Docker daemon secured (not exposed to network)
- [ ] Docker content trust enabled (optional)
- [ ] Docker logging limited (size and rotation)
- [ ] Unnecessary Docker images removed
- [ ] Docker volumes use specific paths (not anonymous)

### Container Security
- [ ] Containers run as non-root user
- [ ] Container resources limited (CPU, memory)
- [ ] Unnecessary capabilities dropped
- [ ] Read-only root filesystem where possible
- [ ] Host network not used (unless necessary)
- [ ] Secrets not passed as environment variables
- [ ] Container images from trusted sources only

## Monitoring & Logging

### Logging
- [ ] Application logs configured
- [ ] Nginx access and error logs enabled
- [ ] System logs monitored
- [ ] Log rotation configured
- [ ] Sensitive data not logged (passwords, tokens, etc.)
- [ ] Logs protected with appropriate permissions

### Monitoring
- [ ] Service health checks configured
- [ ] Disk space monitoring
- [ ] Memory usage monitoring
- [ ] CPU usage monitoring
- [ ] Failed login attempts monitored
- [ ] SSL certificate expiry monitoring
- [ ] Uptime monitoring configured

### Alerting
- [ ] Email alerts for service failures
- [ ] Alerts for high resource usage
- [ ] Alerts for failed login attempts
- [ ] Alerts for SSL certificate expiry
- [ ] Alerts for backup failures

## Backup & Recovery

### Backup Strategy
- [ ] Automated daily backups configured
- [ ] Database backed up
- [ ] Configuration files backed up
- [ ] Workspace data backed up
- [ ] Backup retention policy configured (30 days)
- [ ] Backups stored securely
- [ ] Backup encryption configured (optional)
- [ ] Offsite backup configured (recommended)

### Recovery Plan
- [ ] Restore procedure documented
- [ ] Backup restore tested
- [ ] Recovery time objective (RTO) defined
- [ ] Recovery point objective (RPO) defined
- [ ] Disaster recovery plan documented

## Access Control

### Authentication
- [ ] Strong password policy enforced
- [ ] Password hashing algorithm secure (bcrypt)
- [ ] JWT tokens properly validated
- [ ] Token expiration configured
- [ ] Refresh token strategy implemented
- [ ] Multi-factor authentication considered (future)

### Authorization
- [ ] Role-based access control implemented
- [ ] User permissions properly scoped
- [ ] Admin endpoints protected
- [ ] User isolation enforced (workspace separation)
- [ ] API endpoints require authentication
- [ ] Privilege escalation prevention

### Session Management
- [ ] Session timeout configured
- [ ] Secure cookie flags set (HttpOnly, Secure, SameSite)
- [ ] Session invalidation on logout
- [ ] Concurrent session handling

## Regular Maintenance

### Daily
- [ ] Check service status
- [ ] Review error logs
- [ ] Monitor disk space
- [ ] Verify backups completed

### Weekly
- [ ] Review access logs for anomalies
- [ ] Check for failed login attempts
- [ ] Review Docker container status
- [ ] Check SSL certificate status

### Monthly
- [ ] Review and update firewall rules
- [ ] Review user access and permissions
- [ ] Test backup restore procedure
- [ ] Update system packages
- [ ] Review and rotate secrets (if needed)

### Quarterly
- [ ] Security audit
- [ ] Penetration testing (optional)
- [ ] Review and update security policies
- [ ] Disaster recovery drill
- [ ] Performance optimization review

## Incident Response

### Preparation
- [ ] Incident response plan documented
- [ ] Contact information updated
- [ ] Escalation procedures defined
- [ ] Backup administrator access configured

### Detection
- [ ] Log monitoring tools configured
- [ ] Anomaly detection enabled
- [ ] Alert thresholds configured
- [ ] Incident detection procedures documented

### Response
- [ ] Incident isolation procedures defined
- [ ] Service recovery procedures documented
- [ ] Communication plan established
- [ ] Post-incident review process defined

## Compliance & Documentation

### Documentation
- [ ] Architecture diagram created
- [ ] Configuration documented
- [ ] Deployment procedures documented
- [ ] Security policies documented
- [ ] Runbooks created for common tasks

### Compliance
- [ ] Data protection requirements identified
- [ ] Privacy policy created (if handling user data)
- [ ] Terms of service created
- [ ] GDPR compliance reviewed (if applicable)
- [ ] Data retention policy defined

## Advanced Security (Optional)

### Network Segmentation
- [ ] Separate network for bot containers
- [ ] DMZ for public-facing services
- [ ] Database on isolated network
- [ ] VPN for administrative access

### Additional Hardening
- [ ] AppArmor or SELinux profiles configured
- [ ] Intrusion detection system (IDS) installed
- [ ] Web Application Firewall (WAF) configured
- [ ] DDoS protection configured
- [ ] Security scanning tools integrated

### Secrets Management
- [ ] Vault or secrets manager configured
- [ ] API keys rotated regularly
- [ ] Credentials never in code
- [ ] Environment variables secured
- [ ] Secure key exchange mechanism

---

## Quick Verification Commands

```bash
# Check SSL
echo | openssl s_client -servername your-domain.com -connect your-domain.com:443 2>/dev/null | openssl x509 -noout -dates

# Check firewall
sudo ufw status verbose

# Check file permissions
ls -la /opt/ft-bot/.env.production
ls -la /opt/ft-bot/backend/data/backend.db

# Check security headers
curl -I https://your-domain.com

# Check for security updates
sudo apt list --upgradable

# Check failed login attempts
sudo journalctl -u sshd | grep -i "failed\|invalid"
sudo journalctl -u ft-bot-backend | grep -i "unauthorized\|forbidden"

# Check open ports
sudo netstat -tulpn

# Check running processes
ps aux | grep -E 'nginx|uvicorn|python'

# Check Docker security
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

---

## Security Resources

- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **CIS Benchmarks**: https://www.cisecurity.org/cis-benchmarks/
- **Mozilla SSL Config**: https://ssl-config.mozilla.org/
- **FastAPI Security**: https://fastapi.tiangolo.com/tutorial/security/
- **Docker Security**: https://docs.docker.com/engine/security/

---

## Priority Checklist

If time is limited, ensure these critical items are completed first:

### Critical (Must Have)
1. Strong JWT secret configured
2. HTTPS/SSL enabled
3. Firewall enabled with minimal rules
4. SSH password authentication disabled
5. Environment file permissions set to 600
6. Backups configured and tested
7. Security headers configured in Nginx
8. Rate limiting enabled

### High Priority (Should Have)
9. Fail2Ban configured
10. Log rotation configured
11. Automatic security updates enabled
12. Monitoring configured
13. SSL certificate auto-renewal working
14. Docker daemon secured
15. API documentation disabled in production

### Medium Priority (Nice to Have)
16. Non-standard SSH port
17. Enhanced logging
18. Performance monitoring
19. Alerting system
20. Offsite backups
