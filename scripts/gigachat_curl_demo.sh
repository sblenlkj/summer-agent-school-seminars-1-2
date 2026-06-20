#!/usr/bin/env bash

AUTH_KEY="$GIGACHAT_CREDENTIALS"

AUTH_URL="https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
BASE_URL="https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
MODEL_NAME="GigaChat-2"

ACCESS_TOKEN=$(curl -k -s -X POST "$AUTH_URL" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept: application/json" \
  -H "RqUID: $(uuidgen)" \
  -H "Authorization: Basic $AUTH_KEY" \
  -d "scope=GIGACHAT_API_PERS" | jq -r .access_token)

curl -k -s "$BASE_URL" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d "{
    \"model\": \"$MODEL_NAME\",
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": \"Привет! Объясни простыми словами, что такое API.\"
      }
    ],
    \"temperature\": 0.7,
    \"max_tokens\": 512
  }"