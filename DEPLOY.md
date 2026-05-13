# Deploy gratuito para apresentação

Este guia publica o sistema usando:

- Front-end Angular: Vercel
- Back-end FastAPI: Render
- Banco PostgreSQL: Supabase

## 1. Criar banco no Supabase

1. Acesse `https://supabase.com`.
2. Crie um projeto gratuito.
3. Em `Project Settings > Database`, copie a connection string PostgreSQL.
4. Guarde essa URL para usar como `DATABASE_URL` no Render.

Exemplo:

```text
postgresql://postgres:[SENHA]@db.xxxxx.supabase.co:5432/postgres
```

## 2. Publicar o back-end no Render

1. Acesse `https://render.com`.
2. Crie um `Web Service`.
3. Conecte o repositório do GitHub.
4. Configure:

```text
Root Directory: cadastro/backend
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
Instance Type: Free
```

5. Em `Environment`, adicione:

```text
DATABASE_URL=postgresql://...
JWT_SECRET=crie-uma-chave-grande-e-segura
APP_ENV=production
ENFORCE_HTTPS=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=crie-uma-senha-forte
PIX_KEY=sua-chave-pix
ACADEMY_WHATSAPP=55889993632214
ACADEMY_WHATSAPP_DISPLAY=(88) 9993632214
CORS_ORIGINS=https://SEU-FRONT.vercel.app
```

Depois do deploy, copie a URL pública do Render, por exemplo:

```text
https://ctc-backend.onrender.com
```

## 3. Configurar a URL da API no front-end

Abra:

```text
cadastro/frontend/src/environments/environment.prod.ts
```

Troque:

```ts
apiUrl: 'https://ctc-backend.onrender.com'
```

pela URL real do back-end no Render.

## 4. Publicar o front-end na Vercel

1. Acesse `https://vercel.com`.
2. Importe o repositório do GitHub.
3. Configure:

```text
Root Directory: cadastro/frontend
Framework Preset: Angular
Build Command: npm run build
Output Directory: dist/frontend/browser
```

4. Depois que a Vercel gerar a URL final, volte ao Render e atualize:

```text
CORS_ORIGINS=https://SEU-FRONT.vercel.app
```

## HTTPS obrigatório

Vercel e Render já fornecem HTTPS gratuito nos domínios `.vercel.app` e `.onrender.com`.

No Render, mantenha:

```text
APP_ENV=production
ENFORCE_HTTPS=true
CORS_ORIGINS=https://SEU-FRONT.vercel.app
```

Com isso, o back-end:

- rejeita origens `http://` em produção, exceto localhost;
- redireciona requisições HTTP para HTTPS quando o provedor informar `x-forwarded-proto=http`;
- envia `Strict-Transport-Security` nas respostas.

## Observações importantes

- O plano gratuito do Render pode dormir depois de alguns minutos sem uso. O primeiro acesso pode demorar.
- O banco gratuito do Supabase pode pausar após inatividade.
- Para apresentação, isso é suficiente. Para uso real da academia, o ideal é migrar para plano pago no back-end e banco.
- Em produção, não use `admin123`. O back-end bloqueia inicialização se `APP_ENV=production` estiver usando senha admin padrão ou `JWT_SECRET` fraco.
