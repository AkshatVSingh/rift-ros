# Security and privacy

RIFT is read-only with respect to robot control, but incident bundles can still contain sensitive operational evidence.

Do not attach credentials, private maps, production bags, customer data, proprietary robot configuration, internal hostnames or source code to public issues.

## Sharing bundles

Hostnames are excluded from recorder metadata by default. Before external sharing:

```bash
rift sanitize incident.rift.zip -o share-safe.rift.zip
rift verify share-safe.rift.zip
rift inspect share-safe.rift.zip
```

Sanitization redacts common hostname/user/home-path/IP metadata. It is not a DLP product and cannot recognize every confidential identifier; manual review remains required.

## Archive handling

Packed bundles are verified against an allow-listed file set, checksum/size manifest and conservative uncompressed-size limits before analysis.

## Reporting vulnerabilities

Do not publish security-sensitive robot details in a public issue. Use a private contact channel for vulnerabilities that could expose systems or customer data.
