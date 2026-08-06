# Test kit for hom7-prom-all

Everything needed to generate a real SIP+RTP call (with genuine RTCP) into this
stack, plus synthetic data for the two QoS dashboards that need a dedicated
correlator (xRTP, Horaclifix) that this stack doesn't run.

No Mac or baresip? See `freeswitch/README.md` for a Docker-only alternative:
two FreeSWITCH containers calling each other, with heplify capturing SIP+RTCP
straight from one of the containers.

Two things live outside this folder and must exist before you start:

- **heplify** (capture client) — `bin/heplify_darwin_arm64` is a macOS/arm64
  build with a fix for `lo0` (BSD loopback) capture. Upstream heplify's
  `NewDecoder` only special-cases `LinkTypeEthernet`/`LinkTypeLinuxSLL`/raw-IP
  link types; on macOS, `lo0` reports `LinkTypeNull` (BSD loopback framing — a
  4-byte address-family header, not Ethernet), which falls through to the
  `default: lt = layers.LayerTypeEthernet` case and gets misparsed as
  Ethernet, so every packet captured on loopback is silently dropped as
  "unknown". `heplify-macos-loopback.patch` (in this folder) is the fix,
  applied against `src/decoder/decoder.go` of
  `github.com/sipcapture/heplify`. If the binary here is missing or stale,
  rebuild it:
  ```bash
  git clone https://github.com/sipcapture/heplify.git
  cd heplify
  git apply /path/to/hom7-prom-all/TEST/heplify-macos-loopback.patch
  go build -o heplify_darwin_arm64 ./src/cmd/heplify
  cp heplify_darwin_arm64 /path/to/hom7-prom-all/TEST/bin/
  ```
- **baresip** — a real SIP UA, used instead of SIPp because SIPp doesn't send
  genuine periodic RTCP (SR/RR) — without real RTCP there's nothing for the
  QoS dashboards to show. Install: `brew install baresip`.

`baresip-a` (alice, caller) and `baresip-b` (bob, callee, auto-answers) are
pre-configured accounts. **They hardcode this Mac's LAN IP
(`192.168.1.185`)** — real IPs, not `127.0.0.1`, because baresip can't route
calls to loopback addresses on macOS ("no laddr for 127.0.0.1"). If your IP is
different, update `sip_listen` in both `config` files and the account URIs in
both `accounts` files to match (check with `ipconfig getifaddr en0`).

## 1. Bring the stack up

```bash
cd heplify-server/hom7-prom-all/   # repo root of homer7-docker
docker compose up -d
```

- Homer webapp: http://localhost:9080 (admin/sipcapture)
- Grafana: http://localhost:9030 (admin/admin)

## 2. Start heplify (capture → heplify-server:9060)

```bash
TEST/bin/heplify_darwin_arm64 -S -l info -i lo0 -t pcap -m SIPRTCP -hs 127.0.0.1:9060 -pr 5060-5090 &
```

Leave this running in the background for the whole session.

## 3. Start the callee (bob, auto-answers)

```bash
baresip -f TEST/baresip-b > /tmp/baresip_b.log 2>&1 &
```

## 4. Place a call (alice dials bob)

```bash
sleep 2
baresip -f TEST/baresip-a -e "/dial sip:bob@192.168.1.185:5063" -t 20
```

Runs for ~20s with real bidirectional G.711 audio (a sine tone, via the
`ausine` module — no real mic/speaker needed) and hangs up on its own. Repeat
this command for more calls; alice/bob don't need to be relaunched.

Afterwards the call is queryable in Homer (`Call-ID` search) and in Grafana's
**SIP KPIs**, **SIP Calls & Registers**, **SIP Overview** dashboards.

## 5. QoS dashboards

**QOS RTCP** populates automatically from the real RTCP that baresip sends
during step 4 — no extra step needed, but its four panels are alert-style
(`jitter > 10ms`, `RTT > 4ms`, `packet loss > 10`, `fraction loss > 10`), so a
clean local call usually won't trigger them.

**QOS XRTP** and **QOS Horaclifix** need input formats that only come from a
real SBC (`X-RTP-Stat` SIP header) or a real Horaclifix correlator box —
neither of which we have. `send_hep.py` fakes both by crafting raw HEP v3
packets straight at heplify-server, bypassing heplify/baresip entirely:

```bash
python3 TEST/send_hep.py horaclifix   # -> QOS Horaclifix dashboard
python3 TEST/send_hep.py rtcp         # -> forces bad values into QOS RTCP (jitter/loss)
```

For xRTP, add an `X-RTP-Stat` header to a real call's BYE instead (Horaclifix
and RTCP are pushed directly via HEP because there's no SIP header for them —
xRTP's only carrier *is* a SIP header, so it has to ride a real message). If
you're using the `homer/examples/docker/sipp-test/uac_pcap.xml` SIPp scenario
from the Homer 11 testing session, its BYE already carries a sample
`X-RTP-Stat` header — reuse it, or add one like this to any BYE you send:

```
X-RTP-Stat: CS=123;PS=131918;ES=132131;OS=21106880;SP=0/0;SO=0;QS=-;PR=132118;ER=132131;OR=21138880;CR=0;SR=0;QR=-;PL=22,33;BL=0;LS=0;RB=0/0;SB=-/-;EN=PCMA;DE=PCMA;JI=23,111;DL=34,25,70;IP=192.168.1.185:16000,192.168.1.185:17000
```

### Notes on the Prometheus queries

- Most panels use `changes(metric[1m]) > 0`, meaning the value must actually
  **change** within the last minute — resending the exact same numbers is a
  no-op for these panels. Vary the values (`send_hep.py` randomizes them) each
  time you want a panel to refresh.
- `QOS Horaclifix`'s jitter/loss/latency panels average over 1h (30m for some)
  by design, to avoid firing on a single bad sample. A one-off synthetic
  packet will be diluted by whatever the average already was and may take a
  while to visibly cross the threshold — this is intentional for production,
  not a bug.

## 6. Reset everything (start from scratch)

```bash
cd heplify-server/hom7-prom-all/   # repo root of homer7-docker
docker compose down
rm -rf ./postgres-data && mkdir postgres-data   # wipes captured SIP/HEP calls
echo "" > bootstrap                              # forces homer-app to re-provision
docker volume rm hom7-prom-all_prometheus_data hom7-prom-all_grafana_data
docker compose up -d
```

## Known stack fixes already applied here (not part of this TEST/ folder)

- `../docker-compose.yml`: Grafana pinned to `11.4.0` (was `:master`, a
  nightly build that broke legacy dashboard-variable query migration).
- `../grafana/provisioning/datasources/datasource.yml`: Prometheus datasource
  `uid` pinned to `cMoIj6tGz` to match what every provisioned dashboard
  hardcodes — without this, panels silently query a datasource that doesn't
  exist and show "No data".
- `SIP_KPIs.json`, `SIP_Calls&Registers.json`, `SIP_Methods&Responses.json`,
  `SIP_Overview.json`: the `tn` (target_name) template variable now defaults
  to `includeAll` instead of an empty selection, which previously only
  matched series with an empty `target_name` label.
