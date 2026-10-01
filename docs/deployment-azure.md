# Deploying Factify on Azure (one VM)

One virtual machine runs two containers: the API, and Caddy in front of it for HTTPS
(a free Let's Encrypt certificate, renewed on its own). The database stays on
Supabase and the reading model on Azure OpenAI; nothing else is needed.

Written 2026-09-30. Commands for the VM are Ubuntu; commands for this PC are Git Bash.

## 1. Create the VM (Azure portal)

Use the account that holds the credit. When a student subscription's credit runs out
the whole subscription stops, VM included.

1. **Virtual machines -> Create -> Azure virtual machine.**
2. **Resource group:** new, `factify`. **Name:** `factify-vm`. **Region:** India
   South Central (Hyderabad).
3. **Image:** Ubuntu Server 24.04 LTS - x64.
4. **Size:** `Standard_B4as_v2` (4 vCPU, 16 GiB, about $0.10 an hour). The server
   holds about 4 GB of models when videos are ready at once
   (`FACTIFY_LOCAL__WARM_VIDEO=true`); 8 GiB works with that switched off.

   Azure for Students limits sizes by region. Checked 2026-09-30 on the deploying
   subscription: Central India and UAE North offer 16 GiB sizes but give them a
   quota of 0 (D4as_v5, D4as_v7, E4as_v7 and the rest); India South Central offers
   B4as_v2, B4ms and DS3_v2 with quota. Allowed regions are set by a policy on the
   subscription (`az policy assignment list`); sizes and quota by
   `az vm list-skus --location <region>` and `az vm list-usage --location <region>`.
5. **Authentication:** SSH public key, username `factify`, new key pair - download
   the `.pem` when asked and keep it.
6. **Inbound ports:** allow SSH (22), HTTP (80) and HTTPS (443).
7. **Disks:** OS disk 64 GiB, Standard SSD.
8. **Review + create -> Create.**
9. When it is running: open the VM -> **Public IP address** -> **Configuration** ->
   **DNS name label** = `factify-zeai` -> Save. The server's address is then
   `factify-zeai.indiasouthcentral.cloudapp.azure.com`. The release app is built for this
   name; if it is taken, choose another and rebuild the app (step 7).
10. **Cost Management -> Budgets:** a budget with an alert at 50% and 80% of the
    credit. Stop the VM (**Stop**, not just shut down inside it) when it is not in
    use; a stopped VM costs only its disk.

## 2. Install Docker on the VM

```bash
ssh -i factify-vm_key.pem factify@factify-zeai.indiasouthcentral.cloudapp.azure.com
```

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker factify
exit
```

Log in again so the group applies.

## 3. Send the code

From this PC (repository root), without GitHub:

```bash
git archive --format=tar.gz -o factify.tar.gz HEAD
scp -i factify-vm_key.pem factify.tar.gz factify@factify-zeai.indiasouthcentral.cloudapp.azure.com:~
ssh -i factify-vm_key.pem factify@factify-zeai.indiasouthcentral.cloudapp.azure.com "mkdir -p factify && tar -xzf factify.tar.gz -C factify"
```

(Once the commits are pushed, `git clone` on the VM does the same.)

## 4. Send the models (about 4.9 GB)

The weights are not in the image. Everything in `.cache/models` except `dda` (the
second-opinion picture model, switched off):

```bash
tar -czf models.tgz -C .cache/models --exclude=dda .
scp -i factify-vm_key.pem models.tgz factify@factify-zeai.indiasouthcentral.cloudapp.azure.com:~
ssh -i factify-vm_key.pem factify@factify-zeai.indiasouthcentral.cloudapp.azure.com "mkdir -p factify/models && tar -xzf models.tgz -C factify/models && rm models.tgz"
```

## 5. Send the settings

`.env` holds every key; it never goes into the image or into git.

```bash
scp -i factify-vm_key.pem .env factify@factify-zeai.indiasouthcentral.cloudapp.azure.com:~/factify/.env
```

Then on the VM, in `~/factify/.env`:

- `FACTIFY_CACHE_READS=true` (or delete the line): a repeat is answered at once.
  `deploy/docker-compose.yml` sets this for you as well.
- `FACTIFY_ENVIRONMENT=prod`.
- Keep `FACTIFY_LOCAL__WARM_VIDEO=true` on a 16 GiB VM; set it to `false` on 8 GiB.

And create `~/factify/deploy/.env` with the domain:

```bash
echo "FACTIFY_DOMAIN=factify-zeai.indiasouthcentral.cloudapp.azure.com" > ~/factify/deploy/.env
```

## 6. Start it

```bash
cd ~/factify/deploy
docker compose up -d --build
docker compose logs -f app      # "Uvicorn running", then Ctrl+C
curl https://factify-zeai.indiasouthcentral.cloudapp.azure.com/readyz
```

`{"ready":true,...}` means it is up. The first build takes 10-15 minutes (PyTorch).

To update later: send the new code as in step 3, then `docker compose up -d --build`.

## 7. The app

The release app is built for the server's address:

```bash
cd apps/mobile
flutter build apk --release --dart-define=FACTIFY_API=https://factify-zeai.indiasouthcentral.cloudapp.azure.com
```

The APK is `apps/mobile/build/app/outputs/flutter-apk/app-release.apk`. Install it on
a phone (`adb install -r app-release.apk`, or copy it over and open it).

It is signed with the release key named in `android/key.properties` when that file
exists, and with the debug key otherwise, which is fine for a demo and for
sideloading. The Play Store needs the release key.

## 8. After it works

- Sign-in with email and password works as is. Google sign-in needs an OAuth
  client whose redirect is `https://factify-zeai.indiasouthcentral.cloudapp.azure.com/v1/auth/google/callback`.
- Replace the keys that were pasted in chat (Azure OpenAI, Tavily, Google Vision,
  Groq) in `~/factify/.env`, then `docker compose up -d`.
- "Earlier copies" of a picture needs billing enabled on the Google Cloud project of
  the Vision key; until then it says "not set up on this server".
