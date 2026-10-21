-- Mural de passagem: rode uma vez no SQL Editor do projeto Supabase do mural.
-- Só a chave secreta (guardada no .env de cada PC) acessa as tabelas: o RLS
-- fica ligado e sem políticas, então a chave pública não lê nem escreve nada.

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
