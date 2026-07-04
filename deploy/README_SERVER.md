# Server deploy

Recommended server: Ubuntu 24.04, 4 CPU, 8 GB RAM, 80 GB NVMe.

## Full deploy with data

From the project root run:

```powershell
.\deploy\deploy_all.ps1
```

The script will:

- package the project without local caches/build artifacts;
- package the full `Источники информации` corpus separately;
- upload both archives to `root@5.42.118.92`;
- upload a server `.env` generated from your local `.env`;
- install Docker and Docker Compose plugin;
- start frontend, API, worker, Postgres and Neo4j;
- unpack the corpus into `/opt/science-knot/corpus_ascii`;
- call `/api/demo/register-corpus`.

It does not store the root password in the repository. `ssh`/`scp` will ask for it.

If you need to override the host:

```powershell
.\deploy\deploy_all.ps1 -Server root@5.42.118.92 -PublicIp 5.42.118.92
```

## Light deploy

Local light archive may already be prepared as:

```powershell
nornikel_hack_deploy_light.tgz
```

Upload from your local terminal:

```powershell
scp .\nornikel_hack_deploy_light.tgz root@5.42.118.92:/tmp/
scp .\deploy\server_bootstrap.sh root@5.42.118.92:/tmp/
```

Then on server:

```bash
chmod +x /tmp/server_bootstrap.sh
PUBLIC_IP=5.42.118.92 /tmp/server_bootstrap.sh /tmp/nornikel_hack_deploy_light.tgz
```

The first run creates `/opt/science-knot/.env` and stops. Edit it:

```bash
nano /opt/science-knot/.env
```

Set:

```env
YANDEX_AI_API_KEY=...
YANDEX_AI_FOLDER_ID=...
PUBLIC_API_BASE_URL=http://5.42.118.92:8001
```

Then run again:

```bash
PUBLIC_IP=5.42.118.92 /tmp/server_bootstrap.sh /tmp/nornikel_hack_deploy_light.tgz
```

## URLs

- Frontend: http://5.42.118.92
- API: http://5.42.118.92:8001
- Health: http://5.42.118.92:8001/health

## Notes

- Neo4j and Postgres are not exposed publicly in prod compose.
- Full corpus lives on the server in `/opt/science-knot/corpus_ascii`.
- Light deploy does not include the full corpus. Use `deploy_all.ps1` for the complete server copy.

## SSH troubleshooting

If SSH reaches the banner and then hangs after `SSH2_MSG_KEXINIT sent`, the project deploy cannot start because the connection fails before authentication. Check the server firewall/provider console, try SSH from another network, or run the script from a machine where `ssh root@5.42.118.92` reaches the password prompt.
