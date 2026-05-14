# Authentication

The deployed Nginx front door uses HTTP basic authentication.

The password file is mounted from:

`nginx/.htpasswd`

This file is intentionally ignored by Git. Do not commit live credentials.

## Create Credentials

On the deployment VM, create the password file with:

```bash
mkdir -p /home/traderadmin/veda-trading-ai/nginx
openssl passwd -apr1
```

Then write:

```text
username:hashed-password
```

to:

```text
/home/traderadmin/veda-trading-ai/nginx/.htpasswd
```

Set the file readable by the Nginx container:

```bash
chmod 644 /home/traderadmin/veda-trading-ai/nginx/.htpasswd
```

Restart Nginx:

```bash
cd /home/traderadmin/veda-trading-ai
docker compose up -d nginx
```

## Scope

Basic authentication protects:

- Dashboard at `/`
- API proxy under `/api/`

Direct VM ports should also remain restricted in Azure NSG.
