-- =====================================================================
--  SCHÉMA RELATIONNEL SUPABASE (PostgreSQL) — Prédiction de matchs tennis
-- ---------------------------------------------------------------------
--  Objectif : stocker l'historique des matchs, le référentiel joueurs,
--  les matchs à venir, les prédictions du modèle, le registre des
--  versions de modèle (MLOps) et un journal d'ingestion (pour déclencher
--  le réentraînement).
--
--  Conventions :
--   - Toutes les tables ont un `id` bigint identity (clé technique).
--   - `created_at` / `updated_at` en timestamptz (UTC).
--   - Les clés naturelles servent aux UPSERT idempotents du scraping.
--   - RLS activée : lecture publique (clé anon du frontend), écriture
--     réservée au `service_role` (scripts Python / GitHub Actions).
--
--  À exécuter dans l'éditeur SQL de Supabase (ou via `psql`).
-- =====================================================================

-- Extension utile pour l'indexation trigram (recherche joueur par nom).
create extension if not exists pg_trgm;

-- ---------------------------------------------------------------------
--  Fonction générique : met à jour automatiquement `updated_at`.
--  Réutilisée par plusieurs triggers -> pas de duplication.
-- ---------------------------------------------------------------------
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------
--  Types énumérés : contraignent les valeurs métier et documentent le schéma.
-- ---------------------------------------------------------------------
do $$ begin
  create type tour_type    as enum ('ATP', 'WTA');                     -- circuit
  create type surface_type as enum ('Hard', 'Clay', 'Grass', 'Carpet');-- surface
  create type match_status as enum ('scheduled', 'live', 'completed', 'cancelled');
exception when duplicate_object then null; end $$;


-- =====================================================================
--  1. PLAYERS — référentiel des joueurs (dimension)
-- ---------------------------------------------------------------------
--  Une ligne par joueur. `external_id` = identifiant de la source
--  (ex: player_id Sackmann) pour rendre les UPSERT stables dans le temps.
--  On y garde le classement courant (dénormalisé) pour un affichage rapide
--  côté frontend sans recalcul.
-- =====================================================================
create table if not exists players (
  id             bigint generated always as identity primary key,
  external_id    text unique,                 -- id source (clé naturelle d'UPSERT)
  full_name      text not null,               -- ex: "Djokovic N."
  tour           tour_type not null,          -- ATP ou WTA
  hand           char(1),                     -- 'R' / 'L' / 'U' (unknown)
  country_ioc    char(3),                     -- code pays CIO (ex: SRB)
  birth_date     date,
  height_cm      smallint,
  current_rank   integer,                     -- classement le plus récent connu
  current_points integer,                     -- points ATP/WTA les plus récents
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- Recherche floue par nom (autocomplétion du frontend) + tri par classement.
create index if not exists idx_players_name_trgm on players using gin (full_name gin_trgm_ops);
create index if not exists idx_players_tour_rank on players (tour, current_rank);

drop trigger if exists trg_players_updated on players;
create trigger trg_players_updated before update on players
  for each row execute function set_updated_at();


-- =====================================================================
--  2. MATCHES — historique des matchs terminés (fait)
-- ---------------------------------------------------------------------
--  Table centrale d'entraînement. On stocke gagnant/perdant + le contexte
--  (surface, tour, round) ET les infos PRÉ-MATCH (rang, points) qui sont
--  les seules autorisées comme features (pas de fuite de données).
--
--  Clé naturelle d'UPSERT : (source, external_id). Si la source ne fournit
--  pas d'id, on retombe sur (match_date, winner_id, loser_id, tournament)
--  via l'index unique de secours.
-- =====================================================================
create table if not exists matches (
  id             bigint generated always as identity primary key,
  source         text not null default 'tennis-data',  -- provenance
  external_id    text,                                  -- id match côté source
  match_date     date not null,
  tour           tour_type not null,
  tournament     text not null,                         -- ex: "French Open"
  surface        surface_type not null,
  round          text not null,                         -- ex: "Quarterfinals"
  best_of        smallint not null default 3,

  winner_id      bigint not null references players(id) on delete restrict,
  loser_id       bigint not null references players(id) on delete restrict,

  -- Infos PRÉ-MATCH (features autorisées)
  winner_rank    integer,
  loser_rank     integer,
  winner_points  integer,
  loser_points   integer,

  -- Infos POST-MATCH (jamais utilisées comme features, seulement analyse)
  score          text,
  winner_sets    smallint,
  loser_sets     smallint,

  -- Cotes bookmaker moyennes (baseline de comparaison, feature optionnelle)
  avg_odds_winner numeric(6,3),
  avg_odds_loser  numeric(6,3),

  created_at     timestamptz not null default now(),

  constraint chk_players_distinct check (winner_id <> loser_id)
);

-- UPSERT principal : idempotent sur la clé source.
create unique index if not exists uq_matches_source
  on matches (source, external_id) where external_id is not null;
-- Filet de sécurité quand la source n'a pas d'id de match.
create unique index if not exists uq_matches_natural
  on matches (match_date, winner_id, loser_id, tournament);

-- Index de performance pour l'entraînement (lecture chronologique) et le
-- calcul de la forme par joueur.
create index if not exists idx_matches_date    on matches (match_date);
create index if not exists idx_matches_winner  on matches (winner_id, match_date);
create index if not exists idx_matches_loser   on matches (loser_id, match_date);
-- Sert au déclencheur de réentraînement (comptage des matchs ingérés récemment).
create index if not exists idx_matches_created on matches (created_at);


-- =====================================================================
--  3. UPCOMING_MATCHES — matchs à venir (à prédire)
-- ---------------------------------------------------------------------
--  Alimentée par le scraping du calendrier. `status` suit le cycle de vie ;
--  quand un match passe à `completed`, il peut être promu dans `matches`.
-- =====================================================================
create table if not exists upcoming_matches (
  id             bigint generated always as identity primary key,
  external_id    text unique,                 -- clé naturelle d'UPSERT
  scheduled_at   timestamptz not null,        -- date/heure prévue
  tour           tour_type not null,
  tournament     text not null,
  surface        surface_type not null,
  round          text,
  best_of        smallint not null default 3,

  player1_id     bigint not null references players(id) on delete restrict,
  player2_id     bigint not null references players(id) on delete restrict,

  status         match_status not null default 'scheduled',
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),

  constraint chk_upcoming_distinct check (player1_id <> player2_id)
);

create index if not exists idx_upcoming_status on upcoming_matches (status, scheduled_at);

drop trigger if exists trg_upcoming_updated on upcoming_matches;
create trigger trg_upcoming_updated before update on upcoming_matches
  for each row execute function set_updated_at();


-- =====================================================================
--  4. MODEL_VERSIONS — registre MLOps des modèles entraînés
-- ---------------------------------------------------------------------
--  Chaque réentraînement insère une ligne. `artifact` = modèle sérialisé
--  (joblib) stocké en bytea -> l'inférence recharge le modèle actif
--  directement depuis la base (pas de dépendance à un bucket externe).
--  `is_active` : un seul modèle actif à la fois (index unique partiel).
--  `metrics` / `hyperparams` en JSONB pour tracer la performance et
--  détecter la dérive (drift) en comparant les versions.
-- =====================================================================
create table if not exists model_versions (
  id             bigint generated always as identity primary key,
  version        text not null unique,        -- ex: "2026.07.05-1730"
  algorithm      text not null,               -- ex: "XGBClassifier"
  trained_at     timestamptz not null default now(),
  trained_through date,                        -- date du dernier match utilisé
  n_samples      integer not null,            -- taille du jeu d'entraînement
  feature_names  jsonb not null,              -- ordre des features (train=serve)
  hyperparams    jsonb not null default '{}', -- meilleurs params du GridSearch
  metrics        jsonb not null default '{}', -- {accuracy, log_loss, roc_auc, cv_*}
  artifact       bytea,                       -- bundle joblib (modèle + form store)
  is_active      boolean not null default false,
  created_at     timestamptz not null default now()
);

-- Garantit qu'un seul modèle est marqué actif.
create unique index if not exists uq_model_active
  on model_versions (is_active) where is_active = true;


-- =====================================================================
--  5. PREDICTIONS — probabilités produites par un modèle pour un match
-- ---------------------------------------------------------------------
--  Une prédiction par (match à venir, version de modèle). On garde le
--  vecteur de features (JSONB) pour l'auditabilité / l'explicabilité.
-- =====================================================================
create table if not exists predictions (
  id                 bigint generated always as identity primary key,
  upcoming_match_id  bigint not null references upcoming_matches(id) on delete cascade,
  model_version_id   bigint not null references model_versions(id)  on delete cascade,

  prob_player1       numeric(5,4) not null,   -- P(joueur1 gagne) dans [0,1]
  prob_player2       numeric(5,4) not null,   -- = 1 - prob_player1
  predicted_winner_id bigint references players(id),
  features           jsonb,                   -- features utilisées (debug/XAI)
  created_at         timestamptz not null default now(),

  constraint chk_prob_range check (prob_player1 >= 0 and prob_player1 <= 1),
  -- Une seule prédiction par match et par version de modèle.
  unique (upcoming_match_id, model_version_id)
);

create index if not exists idx_pred_match on predictions (upcoming_match_id);


-- =====================================================================
--  6. DATA_INGESTIONS — journal des exécutions du pipeline data
-- ---------------------------------------------------------------------
--  Chaque run de scraping écrit une ligne. Sert (a) au monitoring et
--  (b) au déclenchement du réentraînement : le script ML compte les
--  nouveaux matchs depuis le dernier entraînement.
-- =====================================================================
create table if not exists data_ingestions (
  id                bigint generated always as identity primary key,
  source            text not null,
  ran_at            timestamptz not null default now(),
  matches_inserted  integer not null default 0,
  matches_updated   integer not null default 0,
  upcoming_upserted integer not null default 0,
  triggered_retrain boolean not null default false,
  notes             text
);


-- =====================================================================
--  SÉCURITÉ — Row Level Security
-- ---------------------------------------------------------------------
--  Le frontend lit avec la clé `anon` (lecture seule). Les scripts Python
--  utilisent la clé `service_role` qui CONTOURNE la RLS (écritures).
--  On expose donc uniquement des policies de LECTURE ci-dessous.
-- =====================================================================
alter table players          enable row level security;
alter table matches          enable row level security;
alter table upcoming_matches enable row level security;
alter table predictions      enable row level security;
alter table model_versions   enable row level security;
alter table data_ingestions  enable row level security;

-- Lecture publique des données nécessaires à l'UI.
do $$ begin
  create policy "read_players"   on players          for select using (true);
  create policy "read_upcoming"  on upcoming_matches for select using (true);
  create policy "read_predict"   on predictions      for select using (true);
  create policy "read_matches"   on matches          for select using (true);
exception when duplicate_object then null; end $$;
-- NB: model_versions et data_ingestions n'ont PAS de policy de lecture
--     publique (données internes) -> accessibles uniquement au service_role.


-- =====================================================================
--  VUE PRATIQUE — matchs à venir + dernière prédiction du modèle actif
-- ---------------------------------------------------------------------
--  Simplifie la requête du frontend : une seule source pour l'affichage
--  des cartes de match avec les noms des joueurs et la probabilité.
-- =====================================================================
create or replace view v_upcoming_with_prediction as
select
  u.id                as upcoming_match_id,
  u.scheduled_at,
  u.tour,
  u.tournament,
  u.surface,
  u.round,
  p1.full_name        as player1_name,
  p1.current_rank     as player1_rank,
  p2.full_name        as player2_name,
  p2.current_rank     as player2_rank,
  pr.prob_player1,
  pr.prob_player2,
  pr.predicted_winner_id,
  mv.version          as model_version
from upcoming_matches u
join players p1 on p1.id = u.player1_id
join players p2 on p2.id = u.player2_id
left join model_versions mv on mv.is_active = true
left join predictions pr
       on pr.upcoming_match_id = u.id
      and pr.model_version_id  = mv.id
where u.status = 'scheduled';
