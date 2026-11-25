# =============================================================================
# Legacy AWS Deployment Configuration (Retained for 7-14 Day Rollback Only)
# =============================================================================
#
# Production deployment has migrated to Hostinger VPS KVM 2:
#   - Active deployment files: deploy/hostinger/
#   - Active CI/CD workflow:   .github/workflows/deploy-hostinger.yml
#   - Deployment guide:        docs/HOSTINGER_VPS_DEPLOYMENT.md
#
# Do NOT delete this directory or terminate existing AWS resources (EC2/RDS/S3)
# until Hostinger cutover has been verified in production for 7-14 days.
# Application-level AWS integrations (Amazon Bedrock, S3, optional SQS/Textract)
# remain supported and are preserved in backend code.
