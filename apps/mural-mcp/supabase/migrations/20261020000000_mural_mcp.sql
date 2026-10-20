-- Mural MCP: tabelas do mural (iguais a plugins/mural/supabase.sql), pessoas autorizadas e estado do OAuth.
-- Tudo com RLS ligado e sem políticas: só a chave de serviço da Edge Function acessa.

create table if not exists public.mural_cartoes (
  id uuid primary key default gen_random_uuid(),
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  de text not null check (char_length(de) between 1 and 40),
  para text not null check (char_length(para) between 1 and 40),
  autor text not null default 'humano' check (autor in ('humano', 'agente')),
  tipo text not null default 'passagem' check (tipo in ('passagem', 'pergunta', 'aviso')),
  status text not null default 'novo' check (status in ('novo', 'lido', 'feito')),
  fixado boolean not null default false,
  titulo text not null check (char_length(titulo) between 1 and 200),
  conteudo text not null default '' check (char_length(conteudo) <= 50000)
);

create table if not exists public.mural_respostas (
  id uuid primary key default gen_random_uuid(),
  cartao_id uuid not null references public.mural_cartoes (id) on delete cascade,
  criado_em timestamptz not null default now(),
  de text not null check (char_length(de) between 1 and 40),
  autor text not null default 'humano' check (autor in ('humano', 'agente')),
  texto text not null check (char_length(texto) between 1 and 20000)
);

create index if not exists mural_cartoes_para_idx on public.mural_cartoes (para, status, atualizado_em desc);
create index if not exists mural_cartoes_de_idx on public.mural_cartoes (de, atualizado_em desc);
create index if not exists mural_respostas_cartao_idx on public.mural_respostas (cartao_id, criado_em);

-- Uma resposta nova sobe o cartão na lista
create or replace function public.mural_tocar_cartao() returns trigger
language plpgsql set search_path = public as $$
begin
  update public.mural_cartoes set atualizado_em = now() where id = new.cartao_id;
  return new;
end $$;

drop trigger if exists mural_respostas_tocar on public.mural_respostas;
create trigger mural_respostas_tocar after insert on public.mural_respostas
  for each row execute function public.mural_tocar_cartao();

alter table public.mural_cartoes enable row level security;
alter table public.mural_respostas enable row level security;

-- Quem pode entrar no mural: o login do GitHub vira o nome da pessoa nos cartões
create table if not exists public.mural_pessoas (
  github text primary key check (github ~ '^[A-Za-z0-9-]{1,39}$'),
  pessoa text not null check (pessoa ~ '^[a-z0-9][a-z0-9_-]{0,39}$'),
  criado_em timestamptz not null default now()
);
create unique index if not exists mural_pessoas_github_ci on public.mural_pessoas (lower(github));

insert into public.mural_pessoas (github, pessoa) values
  ('guicarvalhal8', 'guilherme'),
  ('felippealmeidaa', 'felipe')
on conflict do nothing;

create table if not exists public.mural_oauth_clientes (
  client_id text primary key,
  redirect_uris text[] not null,
  client_name text not null default '',
  criado_em timestamptz not null default now()
);

create table if not exists public.mural_oauth_pendentes (
  estado text primary key,
  client_id text not null references public.mural_oauth_clientes (client_id) on delete cascade,
  redirect_uri text not null,
  code_challenge text not null,
  estado_cliente text not null default '',
  expira_em timestamptz not null
);

create table if not exists public.mural_oauth_codigos (
  hash text primary key,
  client_id text not null references public.mural_oauth_clientes (client_id) on delete cascade,
  redirect_uri text not null,
  code_challenge text not null,
  pessoa text not null,
  expira_em timestamptz not null
);

-- Só o hash SHA-256 dos tokens fica guardado
create table if not exists public.mural_oauth_tokens (
  hash text primary key,
  tipo text not null check (tipo in ('acesso', 'renovacao')),
  client_id text not null references public.mural_oauth_clientes (client_id) on delete cascade,
  pessoa text not null,
  expira_em timestamptz not null,
  criado_em timestamptz not null default now()
);
create index if not exists mural_oauth_tokens_expira_idx on public.mural_oauth_tokens (expira_em);

-- Apaga logins pela metade, códigos e tokens vencidos (rode de vez em quando ou agende com pg_cron)
create or replace function public.mural_oauth_limpar() returns void
language sql set search_path = public as $$
  delete from public.mural_oauth_pendentes where expira_em < now();
  delete from public.mural_oauth_codigos where expira_em < now();
  delete from public.mural_oauth_tokens where expira_em < now();
$$;

alter table public.mural_pessoas enable row level security;
alter table public.mural_oauth_clientes enable row level security;
alter table public.mural_oauth_pendentes enable row level security;
alter table public.mural_oauth_codigos enable row level security;
alter table public.mural_oauth_tokens enable row level security;
