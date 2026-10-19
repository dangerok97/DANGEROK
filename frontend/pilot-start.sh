#!/bin/sh
set -eu
: "${PILOT_BASIC_AUTH_USER:?Missing isolated pilot username}"
: "${PILOT_BASIC_AUTH_PASSWORD:?Missing isolated pilot password}"
: "${PILOT_COOKIE_TOKEN:?Missing isolated pilot cookie token}"
# Nginx conf is generated only inside the runtime container, never in the
# public Expo bundle or GitHub. Credentials never enter Docker build args.
htpasswd -bBc /etc/nginx/.pilot-htpasswd "$PILOT_BASIC_AUTH_USER" "$PILOT_BASIC_AUTH_PASSWORD" >/dev/null
# Prefer the DNS server assigned to this container by Railway.
PILOT_DNS="$(awk '/^nameserver[[:space:]]+/{print $2;exit}' /etc/resolv.conf)"
: "${PILOT_DNS:=127.0.0.11}"
# Nginx resolver requires brackets around an IPv6 literal, e.g. [fd12::10].
case "$PILOT_DNS" in
  *:*) PILOT_DNS="[$PILOT_DNS]" ;;
esac
sed -e "s#__PILOT_COOKIE_TOKEN__#$PILOT_COOKIE_TOKEN#g" \
    -e "s#__PILOT_DNS__#$PILOT_DNS#g" \
    /etc/nginx/pilot.conf.template > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
