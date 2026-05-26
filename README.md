# Sistema de cadastro e pagamentos para Jiu-Jitsu

Projeto inicial com:

- Front-end em Angular
- Back-end em Python com FastAPI
- Cadastro de aluno com usuário, celular, modalidade e dados da ficha impressa
- Perfil com número do aluno, nome completo, idade, calendário de treino e financeiro
- Pagamento via Pix com chave configurada no back-end
- Lembrete de pagamento por WhatsApp em modo demonstracao
- Área de professores com termo assinado, bolsa/desconto, professores e desistentes

## Como rodar o back-end

Entre na pasta:

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

A API ficará em:

```text
http://localhost:8000
```

## Banco de dados

Por padrão, o projeto continua usando SQLite localmente.

Para usar PostgreSQL em hospedagem, configure a variável de ambiente:

```bash
set DATABASE_URL=postgresql://usuario:senha@host:5432/banco
```

Em provedores como Supabase, copie a connection string PostgreSQL e use como `DATABASE_URL`.
Quando essa variável estiver configurada, o back-end cria as tabelas automaticamente no PostgreSQL.

## Executável desktop (rodar no PC sem instalar nada)

É possível empacotar o sistema em um único arquivo `.exe` para Windows. Ao abrir, o servidor sobe automaticamente e o navegador abre na tela inicial.

### Pré-requisitos (instalar uma vez no PC Windows)

- [Node.js](https://nodejs.org) — versão LTS
- [Python](https://www.python.org) — versão 3.11 ou superior (marcar "Add to PATH" na instalação)

### Gerar o .exe

Com os pré-requisitos instalados, dê dois cliques em **`build-windows.bat`** na raiz do projeto. O script vai:

1. Compilar o front-end Angular
2. Copiar os arquivos para dentro do back-end
3. Instalar as dependências Python
4. Gerar o executável com PyInstaller

O arquivo final estará em:

```text
backend\dist\Academia CTC.exe
```

O processo leva entre 3 e 5 minutos na primeira execução.

### Usar o .exe

Basta abrir `Academia CTC.exe`. O navegador abrirá automaticamente em `http://localhost:8000`.

O banco de dados (`jiujitsu.db`) é criado na mesma pasta do `.exe` e persiste entre execuções. Para fazer backup, basta copiar esse arquivo.

### Testar o modo desktop no Mac (desenvolvimento)

```bash
./build-desktop.sh
cd backend && python launcher.py
```

## Deploy gratuito na nuvem

Para publicar uma versão de apresentação usando Vercel, Render e Supabase, veja:

```text
DEPLOY.md
```

## Como rodar o front-end

Em outro terminal, entre na pasta:

```bash
cd frontend
npm install
npm start
```

O sistema ficará em:

```text
http://localhost:4200
```

## Como testar

1. Abra `http://localhost:4200`.
2. Crie um cadastro de aluno.
3. Faça login com o nome de usuário e senha.
4. Veja o perfil, calendário e financeiro.
5. Copie a chave Pix na área financeira.
6. No dia de vencimento, o back-end envia automaticamente um lembrete por WhatsApp se a mensalidade estiver pendente.

## Área administrativa

O back-end cria um professor padrao automaticamente:

```text
Usuário: admin
Senha: admin123
```

Para trocar esses dados, defina as variáveis de ambiente antes de iniciar o back-end:

```bash
set ADMIN_USERNAME=professor
set ADMIN_PASSWORD=uma-senha-forte
```

Na área administrativa, o professor pode:

- clicar no nome do aluno para ver a ficha completa;
- marcar se o termo físico foi assinado;
- registrar bolsa/desconto: `nao`, `sim`, `bolsa parcial`, `com 2 filhos`;
- excluir aluno;
- marcar aluno como desistente;
- ver a lista de alunos que foram e não voltaram;
- cadastrar professores, turmas e horários.

## Configurar WhatsApp real

Se `WHATSAPP_ACCESS_TOKEN` e `WHATSAPP_PHONE_NUMBER_ID` não estiverem configurados, o sistema mostra a mensagem no terminal.

Para enviar WhatsApp real, copie `backend/.env.example` para `backend/.env` e preencha:

```text
WHATSAPP_ACCESS_TOKEN=seu-token-da-meta
WHATSAPP_PHONE_NUMBER_ID=id-do-numero-do-whatsapp-business
WHATSAPP_API_VERSION=v25.0
```

O sistema verifica automaticamente os lembretes a cada 1 hora. Para mudar esse intervalo:

```bash
set REMINDER_CHECK_INTERVAL_SECONDS=1800
```

## Configurar Pix com Mercado Pago

O sistema já tem uma integração inicial com Mercado Pago. Sem token, ele usa a chave Pix manual configurada em `PIX_KEY`.

Para tentar gerar uma cobrança Pix real, configure:

```bash
set MERCADO_PAGO_ACCESS_TOKEN=seu_access_token
set PIX_KEY=sua-chave-pix
```

O token deve ficar apenas no back-end, nunca no Angular.

## Proximos passos recomendados

- Configurar WhatsApp Business Cloud API real.
- Configurar credenciais reais do provedor Pix.
- Criar telas para editar dados de alunos.
- Hospedar o front-end e o back-end em servidores reais.
