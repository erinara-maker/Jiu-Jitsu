# Back-end do sistema de Jiu-Jitsu

Este back-end usa FastAPI, SQLite local ou PostgreSQL em hospedagem, JWT, bcrypt, WhatsApp configurável e integração inicial com Mercado Pago para Pix.

## Como executar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

A API ficará em `http://localhost:8000`.

## Login administrativo

Usuário padrão:

```text
admin
```

Senha padrao:

```text
admin123
```

Você pode trocar usando `ADMIN_USERNAME` e `ADMIN_PASSWORD`.

## Variáveis de ambiente

Copie o arquivo `.env.example` para `.env` dentro da pasta `backend` e preencha os dados reais.

```bash
set JWT_SECRET=uma-chave-grande-e-segura
set DATABASE_URL=postgresql://usuario:senha@host:5432/banco
set APP_ENV=production
set PIX_KEY=sua-chave-pix
set MERCADO_PAGO_ACCESS_TOKEN=seu-token-do-mercado-pago
set WHATSAPP_ACCESS_TOKEN=seu-token-da-meta
set WHATSAPP_PHONE_NUMBER_ID=id-do-numero-do-whatsapp-business
set WHATSAPP_API_VERSION=v25.0
set REMINDER_CHECK_INTERVAL_SECONDS=3600
```

Se `DATABASE_URL` não estiver configurada, o sistema usa o arquivo SQLite local `jiujitsu.db`.
Se `DATABASE_URL` estiver configurada, o sistema usa PostgreSQL e cria as tabelas automaticamente.

Em produção, use `JWT_SECRET` forte e troque `ADMIN_PASSWORD`. O back-end bloqueia inicialização com segredo fraco ou senha padrão quando roda em modo produção/PostgreSQL.

Para envio real, é necessário ter WhatsApp Business Cloud API configurado na Meta. O celular do aluno deve ser cadastrado com DDD; números brasileiros sem código do país recebem `55` automaticamente.

## Observacao

Se o WhatsApp não estiver configurado, o lembrete aparece no terminal. Se `MERCADO_PAGO_ACCESS_TOKEN` não estiver configurado, o sistema usa a chave Pix manual.

Os lembretes de pagamento sao enviados automaticamente quando:

- a mensalidade do aluno está com status `pendente`;
- o aluno está com status `ativo`;
- o dia atual é igual ao dia de pagamento do aluno;
- ainda não foi enviado lembrete para esse aluno nessa data.

## Recursos administrativos

- Ficha completa do aluno baseada na ficha impressa.
- Número sequencial do aluno no formato `001`, `002`, `003`.
- Controle de termo de autorização assinado.
- Controle de bolsa/desconto.
- Lista de alunos desistentes.
- Cadastro de professores com turma e horários.
