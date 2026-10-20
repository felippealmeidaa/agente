# Mural MCP

O Mural de passagem como servidor MCP remoto, com login pelo GitHub. Cada um conecta o próprio Hermes, ou o Claude Code, o Cursor e qualquer outro cliente MCP, e orquestra pela sua máquina. Ninguém copia a chave do banco nem configura "eu" e "parceiro": a identidade vem do login.

- **Onde roda:** numa Edge Function do Supabase (`supabase/functions/mural-mcp`). A chave do banco é injetada pelo próprio Supabase e nunca sai de lá.
- **Login:** OAuth 2.1 com PKCE e registro automático do cliente, que é o que o Hermes e os outros clientes MCP esperam. A autenticação é delegada ao GitHub. Só entram os GitHubs cadastrados na tabela `mural_pessoas`.
- **Ferramentas:** `ler`, `escrever` e `responder`. No Hermes aparecem como `mcp__mural__ler` etc. O plugin `controle` reconhece esses nomes:
  - não pede aprovação para usar o mural;
  - cerca conteúdo suspeito;
  - conta escrever e responder como saída quando a sessão já leu um segredo.
- **Tokens:** só o hash SHA-256 fica no banco. O acesso dura 1 hora e a renovação 60 dias, com rotação a cada uso. O token do GitHub é descartado logo depois do login.

## Montar (uma vez, por um dos dois)

1. **Banco.** No projeto Supabase do mural, aplique a migração. Pode ser pelo terminal:
   ```powershell
   cd apps\mural-mcp
   npx supabase login
   npx supabase link --project-ref <ref>
   npx supabase db push
   ```
   Ou cole `supabase/migrations/20261020000000_mural_mcp.sql` no SQL Editor. Depois cadastre em `mural_pessoas` o login do GitHub de cada pessoa (há um exemplo comentado na migração).
2. **App OAuth no GitHub.** Vá em *Settings → Developer settings → OAuth Apps → New OAuth App* e preencha:
   - **Homepage URL:** `https://<ref>.supabase.co/functions/v1/mural-mcp`
   - **Authorization callback URL:** `https://<ref>.supabase.co/functions/v1/mural-mcp/github/callback`

   Depois de criar, gere um *client secret*.
3. **Segredos e deploy:**
   ```powershell
   npx supabase secrets set GITHUB_CLIENT_ID=<client id> GITHUB_CLIENT_SECRET=<client secret>
   npx supabase functions deploy mural-mcp --no-verify-jwt
   ```

Para pôr mais alguém no mural, inclua uma linha em `mural_pessoas` (github, pessoa). Para tirar alguém, apague a linha: o próximo uso do token já falha.

## Conectar (cada um, no seu PC)

**Hermes.** No `config.yaml` (`%LOCALAPPDATA%\hermes\config.yaml` no Windows):
```yaml
mcp_servers:
  mural:
    url: https://<ref>.supabase.co/functions/v1/mural-mcp
    auth: oauth
```
Depois rode `hermes mcp login mural`. O navegador abre, você entra com o GitHub e pronto.

**Claude Code:**
```powershell
claude mcp add --transport http mural https://<ref>.supabase.co/functions/v1/mural-mcp
```

## Testar localmente

```powershell
cd apps\mural-mcp
npx deno@2.1.4 run --allow-net --allow-env teste/local.ts     # banco em memória e GitHub falso
python -m pytest teste/test_cliente_mcp.py                    # precisa de: mcp, httpx, pytest, anyio
```

O teste usa o SDK MCP oficial em Python, o mesmo do Hermes, e, se achar o repositório, o provedor de login do próprio Hermes. Ele percorre:
- descoberta, registro, login e PKCE;
- as três ferramentas, com duas pessoas conversando;
- a recusa de um GitHub fora da lista;
- a rejeição de token e de PKCE inválidos;
- a rotação do refresh token.
