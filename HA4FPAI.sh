apt install jq curl -y
url="$(curl -fsSL https://api.github.com/repos/WCIS-Team/HA4FPAI/releases/latest \
  | jq -r '.assets[].browser_download_url | select(endswith(".deb"))' | head -n1)" \
&& test -n "$url" \
&& curl -fL "$url" -o latest.deb \
&& apt install ./latest.deb
