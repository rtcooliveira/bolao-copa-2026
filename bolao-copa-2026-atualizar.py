#!/usr/bin/env python3
"""
Bolão Copa 2026 — Auto-atualização de resultados via ESPN API
=============================================================
Uso simples:
    python bolao-copa-2026-atualizar.py

O script:
  1. Busca todos os jogos já finalizados da Copa 2026 na ESPN
  2. Para cada jogo, puxa os detalhes dos gols (marcador, minuto, pênalti, gol contra)
  3. Atualiza o Firebase automaticamente (todos os bolões ou um específico)
  4. Exibe resumo do que foi atualizado

Dependências (apenas):
    pip install requests

Nenhuma service account ou firebase-admin necessário — usa a REST API pública do Firebase.

Argumentos opcionais:
    python bolao-copa-2026-atualizar.py                 # atualiza todos os bolões
    python bolao-copa-2026-atualizar.py <bolao_id>      # atualiza bolão específico
    python bolao-copa-2026-atualizar.py --list          # lista bolões
    python bolao-copa-2026-atualizar.py --dry-run       # mostra sem salvar
"""

import json
import sys
import argparse
from datetime import datetime

try:
    import requests
except ImportError:
    print("ERRO: biblioteca 'requests' não instalada.")
    print("Execute: pip install requests")
    sys.exit(1)

# ─── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────

FIREBASE_DB_URL  = "https://bolao-copa-2026-c99d8-default-rtdb.firebaseio.com"
FIREBASE_ROOT    = "boloes"
ESPN_BASE        = "https://site.api.espn.com/apis/site/v2/sports/soccer"
COPA_SLUG        = "fifa.world"

# ─── MAPEAMENTO ESPN (inglês) → NOME CANÔNICO DO BOLÃO ────────────────────────
# Nomes canônicos devem bater EXATAMENTE com os usados no const GROUPS do app

ESPN_TO_BOLAO = {
    # Grupo A
    "Mexico":                    "México",
    "South Korea":               "Coreia do Sul",
    "South Africa":              "África do Sul",
    "Czech Republic":            "República Checa",
    "Czechia":                   "República Checa",
    # Grupo B
    "Bosnia and Herzegovina":    "Bósnia-Herzegovina",
    "Bosnia & Herzegovina":      "Bósnia-Herzegovina",
    "Bosnia":                    "Bósnia-Herzegovina",
    "Qatar":                     "Catar",
    "Canada":                    "Canadá",
    "Switzerland":               "Suíça",
    # Grupo C
    "Brazil":                    "Brasil",
    "Haiti":                     "Haiti",
    "Morocco":                   "Marrocos",
    "Scotland":                  "Escócia",
    # Grupo D
    "Turkey":                    "Turquia",
    "Türkiye":                   "Turquia",
    "Australia":                 "Austrália",
    "United States":             "EUA",
    "USA":                       "EUA",
    "Paraguay":                  "Paraguai",
    # Grupo E
    "Germany":                   "Alemanha",
    "Ivory Coast":               "Costa do Marfim",
    "Côte d'Ivoire":             "Costa do Marfim",
    "Cote d'Ivoire":             "Costa do Marfim",
    "Curacao":                   "Curaçao",
    "Curaçao":                   "Curaçao",
    "Ecuador":                   "Equador",
    # Grupo F
    "Netherlands":               "Holanda",
    "Sweden":                    "Suécia",
    "Japan":                     "Japão",
    "Tunisia":                   "Tunísia",
    # Grupo G
    "Belgium":                   "Bélgica",
    "Iran":                      "Irã",
    "Egypt":                     "Egito",
    "New Zealand":               "Nova Zelândia",
    # Grupo H
    "Spain":                     "Espanha",
    "Cape Verde":                "Cabo Verde",
    "Uruguay":                   "Uruguai",
    "Saudi Arabia":              "Arábia Saudita",
    # Grupo I
    "France":                    "França",
    "Senegal":                   "Senegal",
    "Norway":                    "Noruega",
    "Iraq":                      "Iraque",
    # Grupo J
    "Argentina":                 "Argentina",
    "Algeria":                   "Argélia",
    "Austria":                   "Áustria",
    "Jordan":                    "Jordânia",
    # Grupo K
    "Portugal":                  "Portugal",
    "DR Congo":                  "RD Congo",
    "Congo":                     "RD Congo",
    "Congo DR":                  "RD Congo",
    "Democratic Republic of Congo": "RD Congo",
    "Colombia":                  "Colômbia",
    "Uzbekistan":                "Uzbequistão",
    # Grupo L
    "England":                   "Inglaterra",
    "Ghana":                     "Gana",
    "Croatia":                   "Croácia",
    "Panama":                    "Panamá",
}

# ─── CC (country code) por time — para artilharia ────────────────────────────
TEAM_CC = {
    "México": "mx", "África do Sul": "za", "Coreia do Sul": "kr", "República Checa": "cz",
    "Bósnia-Herzegovina": "ba", "Canadá": "ca", "Catar": "qa", "Suíça": "ch",
    "Brasil": "br", "Marrocos": "ma", "Haiti": "ht", "Escócia": "gb-sct",
    "Turquia": "tr", "EUA": "us", "Austrália": "au", "Paraguai": "py",
    "Alemanha": "de", "Curaçao": "cw", "Costa do Marfim": "ci", "Equador": "ec",
    "Holanda": "nl", "Japão": "jp", "Suécia": "se", "Tunísia": "tn",
    "Bélgica": "be", "Egito": "eg", "Irã": "ir", "Nova Zelândia": "nz",
    "Espanha": "es", "Uruguai": "uy", "Cabo Verde": "cv", "Arábia Saudita": "sa",
    "França": "fr", "Noruega": "no", "Senegal": "sn", "Iraque": "iq",
    "Argentina": "ar", "Áustria": "at", "Argélia": "dz", "Jordânia": "jo",
    "Portugal": "pt", "Colômbia": "co", "RD Congo": "cd", "Uzbequistão": "uz",
    "Inglaterra": "gb-eng", "Croácia": "hr", "Gana": "gh", "Panamá": "pa",
}

# ─── LOOKUP DE JOGOS DA FASE DE GRUPOS ────────────────────────────────────────
# IDs devem bater com o que o app gera em getGroupMatches():
#   G{grupo}{1-6} onde:
#     1: t[0] vs t[1]   2: t[2] vs t[3]   3: t[0] vs t[2]
#     4: t[1] vs t[3]   5: t[0] vs t[3]   6: t[1] vs t[2]
# Ordem dos times por grupo = ordem em const GROUPS no app

GROUP_MATCH_LOOKUP = {
    # Grupo A: t0=México, t1=África do Sul, t2=Coreia do Sul, t3=República Checa
    frozenset(["México",          "África do Sul"]):     "GA1",
    frozenset(["Coreia do Sul",   "República Checa"]):   "GA2",
    frozenset(["México",          "Coreia do Sul"]):     "GA3",
    frozenset(["África do Sul",   "República Checa"]):   "GA4",
    frozenset(["México",          "República Checa"]):   "GA5",
    frozenset(["África do Sul",   "Coreia do Sul"]):     "GA6",
    # Grupo B: t0=Bósnia-Herzegovina, t1=Canadá, t2=Catar, t3=Suíça
    frozenset(["Bósnia-Herzegovina", "Canadá"]):         "GB1",
    frozenset(["Catar",              "Suíça"]):           "GB2",
    frozenset(["Bósnia-Herzegovina", "Catar"]):          "GB3",
    frozenset(["Canadá",             "Suíça"]):           "GB4",
    frozenset(["Bósnia-Herzegovina", "Suíça"]):          "GB5",
    frozenset(["Canadá",             "Catar"]):           "GB6",
    # Grupo C: t0=Brasil, t1=Marrocos, t2=Haiti, t3=Escócia
    frozenset(["Brasil",   "Marrocos"]): "GC1",
    frozenset(["Haiti",    "Escócia"]):  "GC2",
    frozenset(["Brasil",   "Haiti"]):    "GC3",
    frozenset(["Marrocos", "Escócia"]):  "GC4",
    frozenset(["Brasil",   "Escócia"]):  "GC5",
    frozenset(["Marrocos", "Haiti"]):    "GC6",
    # Grupo D: t0=Turquia, t1=EUA, t2=Austrália, t3=Paraguai
    frozenset(["Turquia",   "EUA"]):       "GD1",
    frozenset(["Austrália", "Paraguai"]):  "GD2",
    frozenset(["Turquia",   "Austrália"]): "GD3",
    frozenset(["EUA",       "Paraguai"]):  "GD4",
    frozenset(["Turquia",   "Paraguai"]):  "GD5",
    frozenset(["EUA",       "Austrália"]): "GD6",
    # Grupo E: t0=Alemanha, t1=Curaçao, t2=Costa do Marfim, t3=Equador
    frozenset(["Alemanha",        "Curaçao"]):         "GE1",
    frozenset(["Costa do Marfim", "Equador"]):          "GE2",
    frozenset(["Alemanha",        "Costa do Marfim"]):  "GE3",
    frozenset(["Curaçao",         "Equador"]):          "GE4",
    frozenset(["Alemanha",        "Equador"]):          "GE5",
    frozenset(["Curaçao",         "Costa do Marfim"]):  "GE6",
    # Grupo F: t0=Holanda, t1=Japão, t2=Suécia, t3=Tunísia
    frozenset(["Holanda", "Japão"]):   "GF1",
    frozenset(["Suécia",  "Tunísia"]): "GF2",
    frozenset(["Holanda", "Suécia"]):  "GF3",
    frozenset(["Japão",   "Tunísia"]): "GF4",
    frozenset(["Holanda", "Tunísia"]): "GF5",
    frozenset(["Japão",   "Suécia"]):  "GF6",
    # Grupo G: t0=Bélgica, t1=Egito, t2=Irã, t3=Nova Zelândia
    frozenset(["Bélgica", "Egito"]):        "GG1",
    frozenset(["Irã",     "Nova Zelândia"]): "GG2",
    frozenset(["Bélgica", "Irã"]):           "GG3",
    frozenset(["Egito",   "Nova Zelândia"]): "GG4",
    frozenset(["Bélgica", "Nova Zelândia"]): "GG5",
    frozenset(["Egito",   "Irã"]):           "GG6",
    # Grupo H: t0=Espanha, t1=Uruguai, t2=Cabo Verde, t3=Arábia Saudita
    frozenset(["Espanha",       "Uruguai"]):       "GH1",
    frozenset(["Cabo Verde",    "Arábia Saudita"]): "GH2",
    frozenset(["Espanha",       "Cabo Verde"]):     "GH3",
    frozenset(["Uruguai",       "Arábia Saudita"]): "GH4",
    frozenset(["Espanha",       "Arábia Saudita"]): "GH5",
    frozenset(["Uruguai",       "Cabo Verde"]):     "GH6",
    # Grupo I: t0=França, t1=Noruega, t2=Senegal, t3=Iraque
    frozenset(["França",  "Noruega"]): "GI1",
    frozenset(["Senegal", "Iraque"]):  "GI2",
    frozenset(["França",  "Senegal"]): "GI3",
    frozenset(["Noruega", "Iraque"]):  "GI4",
    frozenset(["França",  "Iraque"]):  "GI5",
    frozenset(["Noruega", "Senegal"]): "GI6",
    # Grupo J: t0=Argentina, t1=Áustria, t2=Argélia, t3=Jordânia
    frozenset(["Argentina", "Áustria"]):  "GJ1",
    frozenset(["Argélia",   "Jordânia"]): "GJ2",
    frozenset(["Argentina", "Argélia"]):  "GJ3",
    frozenset(["Áustria",   "Jordânia"]): "GJ4",
    frozenset(["Argentina", "Jordânia"]): "GJ5",
    frozenset(["Áustria",   "Argélia"]):  "GJ6",
    # Grupo K: t0=Portugal, t1=Colômbia, t2=RD Congo, t3=Uzbequistão
    frozenset(["Portugal", "Colômbia"]):    "GK1",
    frozenset(["RD Congo", "Uzbequistão"]): "GK2",
    frozenset(["Portugal", "RD Congo"]):    "GK3",
    frozenset(["Colômbia", "Uzbequistão"]): "GK4",
    frozenset(["Portugal", "Uzbequistão"]): "GK5",
    frozenset(["Colômbia", "RD Congo"]):    "GK6",
    # Grupo L: t0=Inglaterra, t1=Croácia, t2=Gana, t3=Panamá
    frozenset(["Inglaterra", "Croácia"]): "GL1",
    frozenset(["Gana",       "Panamá"]):  "GL2",
    frozenset(["Inglaterra", "Gana"]):    "GL3",
    frozenset(["Croácia",    "Panamá"]):  "GL4",
    frozenset(["Inglaterra", "Panamá"]):  "GL5",
    frozenset(["Croácia",    "Gana"]):    "GL6",
}

# Lookup inverso: G-ID → descrição legível
MATCH_ID_TO_DESC = {v: " × ".join(sorted(k)) for k, v in GROUP_MATCH_LOOKUP.items()}

# Home team do bolão para cada partida (t0/t1/t2 conforme definição do app)
# Padrão: match1=t0, match2=t2, match3=t0, match4=t1, match5=t0, match6=t1
MATCH_HOME_TEAM = {
    # Grupo A: t0=México, t1=África do Sul, t2=Coreia do Sul, t3=República Checa
    'GA1': 'México',          'GA2': 'Coreia do Sul',      'GA3': 'México',
    'GA4': 'África do Sul',   'GA5': 'México',             'GA6': 'África do Sul',
    # Grupo B: t0=Bósnia-Herzegovina, t1=Canadá, t2=Catar, t3=Suíça
    'GB1': 'Bósnia-Herzegovina', 'GB2': 'Catar',           'GB3': 'Bósnia-Herzegovina',
    'GB4': 'Canadá',          'GB5': 'Bósnia-Herzegovina', 'GB6': 'Canadá',
    # Grupo C: t0=Brasil, t1=Marrocos, t2=Haiti, t3=Escócia
    'GC1': 'Brasil',          'GC2': 'Haiti',              'GC3': 'Brasil',
    'GC4': 'Marrocos',        'GC5': 'Brasil',             'GC6': 'Marrocos',
    # Grupo D: t0=Turquia, t1=EUA, t2=Austrália, t3=Paraguai
    'GD1': 'Turquia',         'GD2': 'Austrália',          'GD3': 'Turquia',
    'GD4': 'EUA',             'GD5': 'Turquia',            'GD6': 'EUA',
    # Grupo E: t0=Alemanha, t1=Curaçao, t2=Costa do Marfim, t3=Equador
    'GE1': 'Alemanha',        'GE2': 'Costa do Marfim',    'GE3': 'Alemanha',
    'GE4': 'Curaçao',         'GE5': 'Alemanha',           'GE6': 'Curaçao',
    # Grupo F: t0=Holanda, t1=Japão, t2=Suécia, t3=Tunísia
    'GF1': 'Holanda',         'GF2': 'Suécia',             'GF3': 'Holanda',
    'GF4': 'Japão',           'GF5': 'Holanda',            'GF6': 'Japão',
    # Grupo G: t0=Bélgica, t1=Egito, t2=Irã, t3=Nova Zelândia
    'GG1': 'Bélgica',         'GG2': 'Irã',                'GG3': 'Bélgica',
    'GG4': 'Egito',           'GG5': 'Bélgica',            'GG6': 'Egito',
    # Grupo H: t0=Espanha, t1=Uruguai, t2=Cabo Verde, t3=Arábia Saudita
    'GH1': 'Espanha',         'GH2': 'Cabo Verde',         'GH3': 'Espanha',
    'GH4': 'Uruguai',         'GH5': 'Espanha',            'GH6': 'Uruguai',
    # Grupo I: t0=França, t1=Noruega, t2=Senegal, t3=Iraque
    'GI1': 'França',          'GI2': 'Senegal',            'GI3': 'França',
    'GI4': 'Noruega',         'GI5': 'França',             'GI6': 'Noruega',
    # Grupo J: t0=Argentina, t1=Áustria, t2=Argélia, t3=Jordânia
    'GJ1': 'Argentina',       'GJ2': 'Argélia',            'GJ3': 'Argentina',
    'GJ4': 'Áustria',         'GJ5': 'Argentina',          'GJ6': 'Áustria',
    # Grupo K: t0=Portugal, t1=Colômbia, t2=RD Congo, t3=Uzbequistão
    'GK1': 'Portugal',        'GK2': 'RD Congo',           'GK3': 'Portugal',
    'GK4': 'Colômbia',        'GK5': 'Portugal',           'GK6': 'Colômbia',
    # Grupo L: t0=Inglaterra, t1=Croácia, t2=Gana, t3=Panamá
    'GL1': 'Inglaterra',      'GL2': 'Gana',               'GL3': 'Inglaterra',
    'GL4': 'Croácia',         'GL5': 'Inglaterra',         'GL6': 'Croácia',
}

# Mapeamento de round ESPN → label amigável para mata-mata
ESPN_ROUND_LABELS = {
    "Round of 32":   "Oitavas de final",
    "Round of 16":   "Quartas de final",
    "Quarterfinals": "Quartas de final",
    "Semifinals":    "Semifinal",
    "3rd Place":     "Disputa 3º lugar",
    "Final":         "Final",
}

# ─── FIREBASE REST API ─────────────────────────────────────────────────────────

def firebase_get(path):
    url = f"{FIREBASE_DB_URL}/{path}.json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

def firebase_patch(path, data):
    """PATCH — merge raso: só adiciona/atualiza as chaves fornecidas."""
    url = f"{FIREBASE_DB_URL}/{path}.json"
    r = requests.patch(url, json=data, timeout=20)
    r.raise_for_status()
    return r.json()

def firebase_put(path, data):
    """PUT — substitui o nó completamente. PUT com None deleta o nó."""
    url = f"{FIREBASE_DB_URL}/{path}.json"
    r = requests.put(url, json=data, timeout=20)
    r.raise_for_status()
    return r.json()

def firebase_delete(path):
    """DELETE — remove o nó."""
    url = f"{FIREBASE_DB_URL}/{path}.json"
    r = requests.delete(url, timeout=20)
    r.raise_for_status()

def bolao_path(bolao_id):
    return f"{FIREBASE_ROOT}/{bolao_id}"

# ─── ESPN API ──────────────────────────────────────────────────────────────────

def _copa_date_strings():
    """Datas YYYYMMDD de todo o período da Copa 2026 (11/jun a 19/jul)."""
    from datetime import date, timedelta
    d, end, out = date(2026, 6, 11), date(2026, 7, 19), []
    while d <= end:
        out.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return out

def fetch_copa_schedule():
    """Retorna eventos Copa 2026 da ESPN varrendo TODO o período do torneio
    (não só os jogos de hoje). Assim, a cada execução o script re-confere todos
    os jogos finalizados e corrige qualquer placar divergente automaticamente."""
    seen = {}
    for dstr in _copa_date_strings():
        url = f"{ESPN_BASE}/{COPA_SLUG}/scoreboard?dates={dstr}"
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            for ev in r.json().get("events", []):
                seen[ev["id"]] = ev  # dedup por id do evento
        except Exception as e:
            print(f"  [aviso] Falha ao buscar scoreboard {dstr}: {e}")
    return list(seen.values())

def fetch_match_goals(event_id):
    """
    Retorna lista de gols de uma partida finalizada.
    Cada gol: {minute, teamEspn, scorer, penalty, ownGoal}
    """
    url = f"{ESPN_BASE}/{COPA_SLUG}/summary?event={event_id}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        competitions = data.get("header", {}).get("competitions", [])
        if not competitions:
            return []
        details = competitions[0].get("details", [])
        goals = []
        for d in details:
            if not d.get("scoringPlay"):
                continue
            participants = d.get("participants", [])
            scorer = (
                participants[0]["athlete"]["displayName"]
                if participants else "Desconhecido"
            )
            goals.append({
                "minute":   d.get("clock", {}).get("displayValue", "?"),
                "teamEspn": d.get("team", {}).get("displayName", "?"),
                "scorer":   scorer,
                "penalty":  d.get("penaltyKick", False),
                "ownGoal":  d.get("ownGoal", False),
            })
        return goals
    except Exception as e:
        print(f"  [aviso] Não foi possível obter gols do jogo {event_id}: {e}")
        return []

def normalize_team(espn_name):
    """Converte nome ESPN (inglês) para nome canônico do bolão (português)."""
    if espn_name in ESPN_TO_BOLAO:
        return ESPN_TO_BOLAO[espn_name]
    for key, val in ESPN_TO_BOLAO.items():
        if key.lower() == espn_name.lower():
            return val
    print(f"  [aviso] Nome de time não mapeado: '{espn_name}' — usando como está")
    return espn_name

def parse_event(event):
    """Extrai informações relevantes de um evento ESPN."""
    comp = event.get("competitions", [{}])[0]
    state = comp.get("status", {}).get("type", {}).get("name", "")

    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c["homeAway"] == "home"), {})
    away = next((c for c in competitors if c["homeAway"] == "away"), {})

    home_espn = home.get("team", {}).get("displayName", "")
    away_espn = away.get("team", {}).get("displayName", "")

    notes = comp.get("notes", [])
    round_label = ""
    for note in notes:
        if note.get("type") == "event":
            round_label = note.get("value", "")
            break

    return {
        "id":          event["id"],
        "name":        event.get("name", ""),
        "date":        event.get("date", ""),
        "completed":   state in ("STATUS_FULL_TIME", "STATUS_FINAL"),
        "in_progress": state in ("STATUS_IN_PROGRESS", "STATUS_HALFTIME"),
        "home_espn":   home_espn,
        "away_espn":   away_espn,
        "home":        normalize_team(home_espn),
        "away":        normalize_team(away_espn),
        "home_score":  int(home.get("score") or 0),
        "away_score":  int(away.get("score") or 0),
        "round":       round_label,
    }

# ─── LIMPEZA DE DADOS LEGADOS ─────────────────────────────────────────────────

def cleanup_legacy_keys(bolao_id, dry_run=False):
    """
    Remove chaves com IDs antigos (M1-M72) do Firebase, caso existam.
    Esses IDs eram usados por versão antiga do script e o app não os reconhece.
    """
    current_groups = firebase_get(f"boloes/{bolao_id}/realResults/groups") or {}
    legacy = [k for k in current_groups if k.startswith("M") and k[1:].isdigit()]
    if not legacy:
        return
    print(f"  [limpeza] Removendo {len(legacy)} chave(s) legada(s): {', '.join(legacy)}")
    if not dry_run:
        for k in legacy:
            firebase_delete(f"boloes/{bolao_id}/realResults/groups/{k}")
    # Também remove goalScorers legado (chave errada)
    existing = firebase_get(f"boloes/{bolao_id}/realResults") or {}
    if "goalScorers" in existing:
        print(f"  [limpeza] Removendo chave legada 'goalScorers'")
        if not dry_run:
            firebase_delete(f"boloes/{bolao_id}/realResults/goalScorers")

# ─── LÓGICA PRINCIPAL ──────────────────────────────────────────────────────────

def update_bolao(bolao_id, dry_run=False):
    """
    Busca resultados Copa 2026 na ESPN e atualiza o bolão no Firebase.
    """
    print(f"\n{'='*60}")
    print(f"  Bolão ID: {bolao_id}")
    print(f"{'='*60}")

    # Limpar dados legados com IDs errados
    cleanup_legacy_keys(bolao_id, dry_run=dry_run)

    # Estado atual no Firebase
    current = firebase_get(f"boloes/{bolao_id}/realResults") or {}
    current_groups  = current.get("groups", {})
    current_scorers = current.get("topScorers", {})  # formato: {name: {goals, team, cc}}

    # Buscar schedule ESPN
    print("\n→ Buscando jogos da Copa 2026 na ESPN...")
    try:
        events = fetch_copa_schedule()
    except Exception as e:
        print(f"  ERRO ao acessar ESPN: {e}")
        return

    completed   = [e for e in events if parse_event(e)["completed"]]
    in_progress = [e for e in events if parse_event(e)["in_progress"]]
    scheduled   = len(events) - len(completed) - len(in_progress)

    print(f"  Total de jogos: {len(events)} "
          f"({len(completed)} finalizados, {len(in_progress)} ao vivo, {scheduled} agendados)")

    if not completed and not in_progress:
        print("\n  Nenhum jogo finalizado ainda.")
        return

    # ─── Processar jogos finalizados ──────────────────────────────────────────
    new_groups      = {}   # match_id → {home, away}
    new_match_goals = {}   # match_id → [lista de gols]
    unknown         = []   # jogos completos que não mapeamos (mata-mata)

    # Acumula artilheiros: começa do estado atual no Firebase
    all_scorers = {}
    for name, info in current_scorers.items():
        if isinstance(info, dict):
            all_scorers[name] = dict(info)  # {goals, team, cc}

    for ev in events:
        info = parse_event(ev)
        if not info["completed"]:
            continue

        team_pair = frozenset([info["home"], info["away"]])
        match_id  = GROUP_MATCH_LOOKUP.get(team_pair)

        if match_id:
            # Atribui o placar PELO NOME da seleção — esquece quem a ESPN chamou
            # de mandante/visitante. O gol de cada time vai pro slot certo do bolão.
            scores_by_team = {info["home"]: info["home_score"],
                              info["away"]: info["away_score"]}
            bolao_home = MATCH_HOME_TEAM.get(match_id)
            outros     = [t for t in scores_by_team if t != bolao_home]
            bolao_away = outros[0] if outros else None
            if bolao_home in scores_by_team and bolao_away in scores_by_team:
                new_score = {"home": scores_by_team[bolao_home],
                             "away": scores_by_team[bolao_away]}
            else:
                # fallback defensivo (não deveria ocorrer): orientação crua da ESPN
                new_score = {"home": info["home_score"], "away": info["away_score"]}
                print(f"  [aviso] {match_id}: nomes {list(scores_by_team)} não casaram com home={bolao_home} — usei orientação ESPN")
            already   = current_groups.get(match_id)

            if already == new_score:
                continue  # já está atualizado

            new_groups[match_id] = new_score

            # Buscar gols
            goals = fetch_match_goals(info["id"])
            if goals:
                new_match_goals[match_id] = goals
                for g in goals:
                    if not g["ownGoal"]:
                        scorer = g["scorer"]
                        team   = normalize_team(g["teamEspn"])
                        cc     = TEAM_CC.get(team, "")
                        prev   = all_scorers.get(scorer, {})
                        all_scorers[scorer] = {
                            "goals": prev.get("goals", 0) + 1,
                            "team":  team,
                            "cc":    cc,
                        }
        else:
            unknown.append(info)

    # ─── Exibir resumo ────────────────────────────────────────────────────────
    if new_groups:
        print(f"\n  FASE DE GRUPOS — {len(new_groups)} novo(s):")
        for mid in sorted(new_groups):
            score = new_groups[mid]
            desc  = MATCH_ID_TO_DESC.get(mid, mid)
            print(f"    {mid}  {desc}  →  {score['home']}×{score['away']}")
    else:
        print("\n  Grupos: nenhuma novidade.")

    if new_match_goals:
        print(f"\n  DETALHES DE GOLS:")
        for mid, goals in new_match_goals.items():
            score = new_groups.get(mid, {})
            desc  = MATCH_ID_TO_DESC.get(mid, mid)
            s_str = f"{score.get('home','?')}×{score.get('away','?')}"
            print(f"    {mid} {desc} ({s_str}):")
            for g in goals:
                pk  = " (pên.)"       if g["penalty"] else ""
                og  = " (gol contra)" if g["ownGoal"] else ""
                print(f"      {g['minute']:>3}'  {g['scorer']}{pk}{og}  [{g['teamEspn']}]")

    if unknown:
        print(f"\n  MATA-MATA — {len(unknown)} jogo(s) finalizado(s) (M-IDs a confirmar):")
        for m in unknown:
            if m["home_score"] > m["away_score"]:
                vencedor = m["home"]
            elif m["away_score"] > m["home_score"]:
                vencedor = m["away"]
            else:
                vencedor = "Prorrogação/pênaltis"
            rd = ESPN_ROUND_LABELS.get(m["round"], m["round"] or "Knockout")
            print(f"    [{rd}]  {m['home']} {m['home_score']}×{m['away_score']} {m['away']}"
                  f"  →  {vencedor}")
        print("    → Informe os M-IDs para que eu salve os vencedores no Firebase.")

    if all_scorers:
        top5 = sorted(all_scorers.items(), key=lambda x: -x[1].get("goals", 0))[:5]
        print(f"\n  ARTILHARIA (top-5):")
        for i, (name, info) in enumerate(top5, 1):
            print(f"    {i}. {name} ({info.get('team','?')}) — {info.get('goals','?')} gol(s)")

    # ─── Salvar no Firebase ────────────────────────────────────────────────────
    if not new_groups and not new_match_goals:
        print("\n  ✓ Firebase já está atualizado.")
        return

    if dry_run:
        print("\n  [DRY-RUN] Nenhuma alteração salva no Firebase.")
        return

    saved = 0
    if new_groups:
        firebase_patch(f"boloes/{bolao_id}/realResults/groups", new_groups)
        saved += len(new_groups)

    if new_match_goals:
        for mid, goals in new_match_goals.items():
            firebase_put(f"boloes/{bolao_id}/realResults/matchGoals/{mid}", goals)

    if all_scorers:
        firebase_put(f"boloes/{bolao_id}/realResults/topScorers", all_scorers)

    print(f"\n  ✓ {saved} resultado(s) e {len(new_match_goals)} detalhe(s) de gols salvos.")


def update_knockout_winner(bolao_id, match_id, winner, dry_run=False):
    """
    Registra manualmente o vencedor de um jogo de mata-mata.
    """
    if not dry_run:
        firebase_patch(
            f"boloes/{bolao_id}/realResults/knockout",
            {match_id: winner}
        )
    print(f"  {'[DRY-RUN] ' if dry_run else ''}✓ {match_id}: vencedor = {winner}")


def update_bonus(bolao_id, key, value, dry_run=False):
    """
    Atualiza um bônus (brazilStage, topScorer, thirdPlace, runnerUp, champion).
    """
    valid_keys = {"brazilStage", "topScorer", "thirdPlace", "runnerUp", "champion"}
    if key not in valid_keys:
        print(f"  ERRO: chave '{key}' inválida. Opções: {', '.join(valid_keys)}")
        return
    if not dry_run:
        firebase_patch(
            f"boloes/{bolao_id}/realResults/bonuses",
            {key: value}
        )
    labels = {
        "brazilStage": "Brasil até", "topScorer": "Artilheiro",
        "thirdPlace": "3º lugar",    "runnerUp": "Vice-campeão",
        "champion": "Campeão"
    }
    print(f"  {'[DRY-RUN] ' if dry_run else ''}✓ {labels[key]}: {value}")


def show_current_results(bolao_id):
    """Exibe os resultados reais registrados no Firebase."""
    results = firebase_get(f"boloes/{bolao_id}/realResults") or {}
    if not results:
        print("  (nenhum resultado registrado ainda)")
        return

    groups = results.get("groups", {})
    if groups:
        print(f"\n  FASE DE GRUPOS ({len(groups)} jogo(s) registrado(s)):")
        for mid in sorted(groups):
            score = groups[mid]
            desc  = MATCH_ID_TO_DESC.get(mid, mid)
            print(f"    {mid}  {desc}  {score.get('home','?')}×{score.get('away','?')}")

    knockout = results.get("knockout", {})
    if knockout:
        print(f"\n  MATA-MATA ({len(knockout)} jogo(s)):")
        for mid, winner in sorted(knockout.items()):
            print(f"    {mid}: {winner}")

    scorers = results.get("topScorers", {})
    if scorers:
        ranking = sorted(scorers.items(), key=lambda x: -x[1].get("goals", 0) if isinstance(x[1], dict) else -x[1])[:10]
        print(f"\n  ARTILHARIA (top-10):")
        for i, (name, info) in enumerate(ranking, 1):
            goals = info.get("goals", info) if isinstance(info, dict) else info
            team  = info.get("team", "?")   if isinstance(info, dict) else "?"
            print(f"    {i}. {name} ({team}) — {goals} gol(s)")

    bonuses = results.get("bonuses", {})
    if bonuses:
        labels = {
            "brazilStage": "Brasil até",  "topScorer": "Artilheiro",
            "thirdPlace":  "3º lugar",    "runnerUp":  "Vice-campeão",
            "champion":    "Campeão"
        }
        print(f"\n  BÔNUS:")
        for k, v in bonuses.items():
            print(f"    {labels.get(k, k)}: {v}")


def list_bolaos():
    """Lista todos os bolões existentes no Firebase."""
    bolaos = firebase_get("boloes") or {}
    if not bolaos:
        print("  Nenhum bolão encontrado.")
        return []
    ids = []
    for bolao_id, data in bolaos.items():
        code = data.get("code", "?")
        name = data.get("name", "(sem nome)")
        n    = len(data.get("participants", {}))
        print(f"  [{code}]  {name}  —  ID: {bolao_id}  —  {n} participante(s)")
        ids.append(bolao_id)
    return ids


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Atualiza resultados do Bolão Copa 2026 via ESPN API.'
    )
    parser.add_argument(
        'bolao_id', nargs='?', default=None,
        help='ID do bolão a atualizar (omita para todos). Use "update" para atualizar todos.'
    )
    parser.add_argument(
        '--list', action='store_true',
        help='Lista todos os bolões sem atualizar.'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Mostra o que seria atualizado sem salvar no Firebase.'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  Bolão Copa 2026 — Atualizador de Resultados")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    if args.list:
        print("\n📋 Bolões encontrados:\n")
        list_bolaos()
        return

    if args.dry_run:
        print("\n⚠️  MODO DRY-RUN — nenhuma alteração será salva.\n")

    # "update" como argumento posicional equivale a "todos os bolões"
    target_id = args.bolao_id
    if target_id and target_id.lower() == 'update':
        target_id = None

    if target_id:
        update_bolao(target_id, dry_run=args.dry_run)
    else:
        print("\n→ Buscando todos os bolões...\n")
        ids = list_bolaos()
        if not ids:
            print("\n  Nenhum bolão encontrado.")
            return
        print(f"\n→ Atualizando {len(ids)} bolão(ões)...\n")
        for bid in ids:
            update_bolao(bid, dry_run=args.dry_run)

    print("\n✓ Concluído.\n")


if __name__ == '__main__':
    main()