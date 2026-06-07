FROM nodered/node-red:latest

COPY package.json /data/package.json
RUN cd /data && npm install --omit=dev --no-audit --no-fund

COPY flows/flows.json /data/flows.json

ENV FLOWS=flows.json
ENV NODE_RED_ENABLE_SAFE_MODE=false
