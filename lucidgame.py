# PATCH CHECK:
# 기능을 추가하거나 동작을 바꿀 때는 관련 도움말, 관리자 도움말,
# 슬래시 명령 설명, 버튼/안내 메시지도 함께 확인하고 필요 시 갱신한다.

import discord
from discord.ext import commands, tasks
from discord import app_commands
import atexit
import asyncio
import copy
import base64
import hashlib
import io
import json
import os
import re
import shutil
import signal
import time
import uuid
import random
import secrets
import logging
import itertools
import threading
import difflib
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Union

import match_stats
import screenshot_stats
import rofl
try:
    import rofl_combat_checkpoint
except ImportError:
    rofl_combat_checkpoint = None
import lucidgame_rules as rules
import lucidgame_guides as guides
import lucidgame_server_admin as server_admin
import lucidgame_profiles as profiles
import lucidgame_replays as replays
import lucidgame_participation as participation
import lucidgame_matches as matches
import lucidgame_storage as storage
from queue_controller import QueueController

try:
    import socketio
except ImportError:
    socketio = None

try:
    from chzzk_bridge import ChzzkApi, ChzzkConfig, ChzzkTokenStore, ensure_fresh_access_token
except ImportError:
    ChzzkApi = None
    ChzzkConfig = None
    ChzzkTokenStore = None
    ensure_fresh_access_token = None

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None
    Jsonb = None

MPLCONFIG_DIR = os.path.join(os.getenv("DATA_DIR", "."), ".matplotlib")
os.makedirs(MPLCONFIG_DIR, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", MPLCONFIG_DIR)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
except ImportError:
    matplotlib = None
    plt = None
    MaxNLocator = None

# ==============================================================================
# [봇 기본 설정 및 전역 변수 선언]
# ==============================================================================
# 시스템 로그 출력을 위한 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LucidBot")
LUCIDGAME_BUILD_TAG = "queue-restore-guard-adc-death-efficiency-20260820"
logger.info("LucidGame build tag: %s", LUCIDGAME_BUILD_TAG)

# 봇 토큰 및 데이터 파일 경로 설정
TOKEN = os.environ["LucidGame_TOKEN"]

DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DM_COMMAND_LOCK_DIR = os.path.join(DATA_DIR, ".dm_command_locks")
DATABASE_URL = os.getenv("DATABASE_URL")
DB_STATE_KEY = "lucidgame_user_data"
DB_LEGACY_TABLE = "lucid_bot_state"
DB_GUILD_TABLE = "lucid_guild_state"

LOCAL_SEED_FILE = "lucid_game_data.json"
LUCID_FILE = os.path.join(DATA_DIR, LOCAL_SEED_FILE)
DB_PENDING_FILE = f"{LUCID_FILE}.db_pending"
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
MAX_BACKUPS = int(os.getenv("MAX_DATA_BACKUPS", "50"))
MMR_SCALE_VERSION = int(getattr(rules, "MMR_SCALE_VERSION", 2))
MMR_SCALE_VERSION_KEY = "_mmr_scale_version"
TEAM_MMR_ADJUSTMENT_CAP = 4
AI_MMR_ADJUSTMENT_CAP = 4
TEAM_AI_COMBINED_ADJUSTMENT_CAP = 7
AI_MMR_APPLIED_KEY = "ai_mmr_applied_v2"


def acquire_dm_command_lock(interaction_id, ttl_seconds=600):
    os.makedirs(DM_COMMAND_LOCK_DIR, exist_ok=True)
    now_ts = time.time()
    try:
        for filename in os.listdir(DM_COMMAND_LOCK_DIR):
            path = os.path.join(DM_COMMAND_LOCK_DIR, filename)
            try:
                if now_ts - os.path.getmtime(path) > ttl_seconds:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass

    lock_path = os.path.join(DM_COMMAND_LOCK_DIR, f"{interaction_id}.lock")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(str(now_ts))
        return True
    except FileExistsError:
        return False

PROMO_FOOTER = "현직 코치들의 전문적인 피드백이 궁금하다면? 프로필 링크 클릭"
MATCH_HISTORY_KEY = "_match_history"
RANKING_BOARD_KEY = "_ranking_board"
WEEKLY_MVP_BOARD_KEY = "_weekly_mvp_board"
LEAGUE_ROUND_KEY = "_league_round"
LEAGUE_SERIES_ROUND_KEY = "_league_series_round"
ARAM_LEAGUE_ROUND_KEY = "_aram_league_round"
LEAGUE_CHAMPIONS_KEY = "_league_champions"
TITLE_SYSTEM_KEY = "_title_system"
FIRST_COLLECTOR_TITLE = "📜 첫 번째 수집가"
RANKING_REFRESH_KEY = "_ranking_refresh"
WINRATE_REIGN_REFRESH_KEY = "_winrate_reign_refresh"
MATCH_OUTPUT_CHANNEL_KEY = "_match_output_channel"
LEAGUE_OUTPUT_CHANNEL_KEY = "_league_output_channel"
LEAGUE_SIM_OUTPUT_CHANNEL_KEY = "_league_sim_output_channel"
MATCH_VOICE_CATEGORY_KEY = "_match_voice_category"
ACTIVE_GAMES_KEY = getattr(storage, "ACTIVE_GAMES_KEY", "_active_games_v1")
ACTIVE_GAME_STORAGE_READY = all(
    hasattr(storage, name)
    for name in ("collect_member_ids", "restore_active_game_value", "_MISSING_MEMBER")
)
HELP_GUIDE_KEY = "_help_guide"
ADMIN_HELP_GUIDE_KEY = "_admin_help_guide"
STREAMING_HELP_GUIDE_KEY = "_streaming_help_guide"
CHZZK_PARTICIPATION_PANEL_KEY = "_chzzk_participation_panel"
HELP_GUIDE_FORUM_THREADS_KEY = "forum_threads"
HELP_GUIDE_FORUM_LAYOUT_VERSION = 2
ANNOUNCEMENT_CHANNEL_KEY = "_announcement_channel"
PATCHNOTE_CHANNEL_KEY = "_patchnote_channel"
FEEDBACK_ALERT_CHANNEL_KEY = "_feedback_alert_channel"
FEEDBACK_PANEL_CHANNEL_KEY = "_feedback_panel_channel"
FEEDBACK_PANEL_MESSAGE_KEY = "_feedback_panel_message"
REPORT_CHANNEL_KEY = "_report_channel"
REPORT_PANEL_KEY = "_report_panel"
REPORT_LOG_KEY = "_reports"
REPORT_LOG_LIMIT = 500
PATCHNOTE_SETUP_DM_SENT_KEY = "_patchnote_setup_dm_sent"
TIER_REQUEST_CHANNEL_KEY = "_tier_request_channel"
TIER_MANAGEMENT_CHANNEL_KEY = "_tier_management_channel"
CHZZK_CHAT_TIER_REGISTRATION_KEY = "_chzzk_chat_tier_registration_enabled"
AUTO_SUMMONER_REGISTRATION_CHANNEL_KEY = "_auto_summoner_registration_channel"
CHAMPION_DATA_CACHE_KEY = "_champion_data_cache"
PARTICIPATION_CHANNEL_KEY = "_participation_channel"
PARTICIPATION_PANEL_KEY = "_participation_panel"
PARTICIPATION_RECRUITMENTS_KEY = "_participation_recruitments"
PARTY_CHANNEL_KEY = "_party_channel"
PARTY_PANEL_KEY = "_party_panel"
PARTY_ROOMS_KEY = "_party_rooms"
PARTY_ADMIN_CHANNEL_KEY = "_party_admin_channel"
PARTY_ADMIN_PANEL_KEY = "_party_admin_panel"
EVENT_SPONSOR_CHANNEL_KEY = "_event_sponsor_channel"
EVENT_SPONSOR_PANEL_KEY = "_event_sponsor_panel"
EVENT_SPONSOR_EVENTS_KEY = "_event_sponsor_events"
MATCH_RECORD_PANEL_KEY = "_match_record_panel"
TEMP_VOICE_TRIGGER_CHANNEL_KEY = "_temp_voice_trigger_channel"
TEMP_VOICE_PANEL_CHANNEL_KEY = "_temp_voice_panel_channel"
TEMP_VOICE_CHANNELS_KEY = "_temp_voice_channels"
MEMBER_AUDIT_LOG_CHANNEL_KEY = "_member_audit_log_channel"
MEMBER_AUDIT_STATE_KEY = "_member_audit_state"
CHAT_LOG_KEY = "_chat_logs"
MATCH_ADMIN_ROLE_KEY = "_match_admin_role_id"
REGISTERED_MEMBER_ROLE_NAME = "멤버"
GUEST_ROLE_NAME_KEYWORD = "게스트"
MEMBER_WELCOME_DM_ENABLED_KEY = "_member_welcome_dm_enabled"
MEMBER_WELCOME_DM_TITLE_KEY = "_member_welcome_dm_title"
MEMBER_WELCOME_DM_MESSAGE_KEY = "_member_welcome_dm_message"
MEMBER_WELCOME_DM_IMAGE_KEY = "_member_welcome_dm_image"
GLOBAL_ANNOUNCEMENT_ENABLED_KEY = "_global_announcement_enabled"
FEATURE_FLAGS_KEY = "_feature_flags"
PATCH_SUMMARY_PROMO_SENT_KEY = "_patch_summary_promo_sent"
BOT_OWNER_IDS = {"836123126706208819", "1331862131376787569"}
SUPPORT_DM_OWNER_ID = 836123126706208819
CHZZK_AUTH_BASE_URL = os.getenv("CHZZK_AUTH_BASE_URL", "https://lucid-chzzk-auth.onrender.com").rstrip("/")
CHZZK_USER_COOLDOWN_SECONDS = float(os.getenv("CHZZK_USER_COOLDOWN_SECONDS", "4"))
CHZZK_TIER_REQUEST_DEDUPE_SECONDS = int(os.getenv("CHZZK_TIER_REQUEST_DEDUPE_SECONDS", "300"))
DDRAGON_BASE_URL = "https://ddragon.leagueoflegends.com"
DDRAGON_LOCALE = os.getenv("DDRAGON_LOCALE", "ko_KR")
CHAMPION_DATA_FILTER_VERSION = 2
LOCAL_EMOJI_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "emojis")
TEAM_SEPARATION_KEY = "_team_separations"
WINRATE_REIGN_KEY = "_winrate_reign"
HELP_GUIDE_EDIT_DELAY_SECONDS = float(os.getenv("HELP_GUIDE_EDIT_DELAY_SECONDS", "0.7"))
AUTO_GUILD_REFRESH_DELAY_SECONDS = float(os.getenv("AUTO_GUILD_REFRESH_DELAY_SECONDS", "1.5"))
MATCH_ENABLED_KEY = "_match_enabled"
MATCH_BLOCKED_ROLE_KEY = "_match_blocked_role_id"
MATCH_FREQUENCY_KEY = "_match_frequency"
MATCH_START_WAIT_KEY = "_match_start_wait"
RESET_START_WAIT_KEY = "_reset_start_wait"
MAX_MATCH_HISTORY = int(os.getenv("MAX_MATCH_HISTORY", "200"))
CHAT_LOG_SAVE_INTERVAL_SECONDS = 30
CHAT_LOG_LAST_SAVE_AT = {}
HALL_OF_FAME_MIN_ROLE_GAMES = 5
HALL_OF_FAME_ROOKIE_MAX_GAMES = 20
_EDIT_UNSET = object()
HALL_OF_FAME_WINRATE_MIN_GAMES = 10
HALL_OF_FAME_TOP_LIMIT = 5
WINRATE_REIGN_TOP_LIMIT = 3
WINRATE_REIGN_START_DATE = "2026-06-28"
QUEUE_ENTRY_TIMEOUT_SECONDS = 90 * 60
KST = rules.KST
ARENA_QUEUE_NUM = 10
ARENA_PLAYER_COUNT = 18
ARENA_TEAM_COUNT = 6
ARENA_TEAM_SIZE = 3
EVENT_MODE_KEY = "arena_3x6"
EVENT_MODE_NAME = "아레나(3x6)"
LEAGUE_QUEUE_KEY = "league"
LEAGUE_SIM_QUEUE_KEY = "league_sim"
LEAGUE_SERIES_QUEUE_KEY = "league_series"
LEAGUE_SERIES_SIM_QUEUE_KEY = "league_series_sim"
LEAGUE_SERIES_SIM_LAST_TEAM_COUNT_KEY = "_league_series_sim_last_team_count"
LEAGUE_MODE_KEY = "league_4team"
LEAGUE_SERIES_MODE_KEY = "league_series"
LEAGUE_MODE_NAME = "협곡 리그전"
LEAGUE_SERIES_MODE_NAME = "협곡 리그전"
LEAGUE_TITLE_NAME = "협곡 토너먼트"
LEAGUE_SIM_LABEL = "협곡 리그전(시뮬레이션)"
LEAGUE_SERIES_SIM_LABEL = "협곡 리그전(시뮬레이션)"
LEAGUE_PLAYER_COUNT = 20
LEAGUE_TEAM_COUNT = 4
LEAGUE_SERIES_MAX_TEAM_COUNT = 8
LEAGUE_SERIES_MIN_TEAM_COUNT = 3
LEAGUE_SERIES_MAX_PLAYER_COUNT = LEAGUE_SERIES_MAX_TEAM_COUNT * 5
LEAGUE_CHAMPION_NAME_TIMEOUT_SECONDS = 60 * 60
LEAGUE_TEAM_GAP_SOFT_LIMIT = 400
LEAGUE_LANE_GAP_SOFT_LIMIT = 1200
LEAGUE_LANE_GAP_HEAVY_LIMIT = 1500
LEAGUE_SERIES_TEAM_GAP_SOFT_LIMIT = 600
LEAGUE_SERIES_LANE_GAP_HEAVY_LIMIT = 1100
LEAGUE_TEAM_GAP_LIMIT_BY_COUNT = {
    3: 400,
    4: 500,
    5: 600,
    6: 700,
    7: 1000,
    8: 1000,
}
LEAGUE_TEAM_GAP_FALLBACK_LIMITS = (1100, 1200)
LEAGUE_HIGH_TIER_PERCENT = 30
LEAGUE_ELITE_TIER_PERCENT = 15
LEAGUE_HIGH_TIER_COUNT_PENALTY = 10000
LEAGUE_HIGH_TIER_SPREAD_PENALTY = 5000
LEAGUE_ELITE_TIER_COUNT_PENALTY = 20000
LEAGUE_ELITE_TIER_SPREAD_PENALTY = 9000
LEAGUE_HIGH_TIER_SCORE_SPREAD_WEIGHT = 1
LEAGUE_ELITE_EMPTY_TEAM_PENALTY = 14000
LEAGUE_ELITE_EMPTY_LOW_TOTAL_WEIGHT = 35
LEAGUE_ELITE_EMPTY_IMPACT_LOW_WEIGHT = 12
LEAGUE_ELITE_EMPTY_IMPACT_FLOOR_GAP = 240
LEAGUE_IMPACT_HIGH_ROLES = ("정글", "원딜")
LEAGUE_IMPACT_HIGH_STACK_PENALTY = 900
LEAGUE_DOUBLE_IMPACT_HIGH_PENALTY = 1800
ARAM_QUEUE_KEY = "aram"
ARAM_MODE_KEY = "aram_5v5"
ARAM_MODE_NAME = "칼바람 나락"
ARAM_PLAYER_COUNT = 10
ARAM_LEAGUE_QUEUE_KEY = "aram_league"
ARAM_LEAGUE_MODE_KEY = "aram_league_series"
ARAM_LEAGUE_MODE_NAME = "칼바람 리그전"
ARAM_LEAGUE_MIN_TEAM_COUNT = 3
ARAM_LEAGUE_MAX_TEAM_COUNT = 8
ARAM_LEAGUE_MAX_PLAYER_COUNT = ARAM_LEAGUE_MAX_TEAM_COUNT * 5
LOW_TIER_QUEUE_KEY = "lowtier"
LOW_TIER_MODE_KEY = "lowtier_5v5"
LOW_TIER_MODE_NAME = "저티어 큐"
LOW_TIER_MMR_LIMIT = 1200
MMR_EVAL_REQUIRED_COUNT = 1
NOBAN_QUEUE_NUM = 6
NOBAN_MODE_KEY = "noban_5v5"
NOBAN_MODE_NAME = "노밴 모드"
LOW_TIER_DELTA_PRESETS = {
    "적음": {"placement_delta": 15, "regular_delta": 8},
    "보통": {"placement_delta": 12, "regular_delta": 6},
    "많음": {"placement_delta": 10, "regular_delta": 5},
}
LINEUP_PERM_LIMIT = 24
MATCH_FREQUENCY_PRESETS = {
    "적음": {
        "label": "내전 적은 서버",
        "placement_games": 5,
        "placement_delta": 40,
        "regular_delta": 20,
    },
    "보통": {
        "label": "내전 적당한 서버",
        "placement_games": 8,
        "placement_delta": 30,
        "regular_delta": 15,
    },
    "많음": {
        "label": "내전 많은 서버",
        "placement_games": 10,
        "placement_delta": 25,
        "regular_delta": 15,
    },
}
DEFAULT_MATCH_FREQUENCY = "보통"

# 수동 임시배치: 랭크 표본이 부족한 유저를 실제 내전으로 빠르게 보정한다.
# 내전이 적은 서버는 적은 경기 + 큰 변동폭, 많은 서버는 많은 경기 + 작은 변동폭.
PROVISIONAL_MMR_PRESETS = {
    "적음": {"games": 3, "delta": 100},
    "보통": {"games": 5, "delta": 80},
    "많음": {"games": 7, "delta": 65},
}
PROVISIONAL_MMR_KEY = "provisional_mmr"
PROVISIONAL_ALL_ROLES_VALUE = "전체"
PROVISIONAL_AI_TOTAL_DELTA_CAP = 140
PROVISIONAL_AI_MIN_DIRECTIONAL_DELTA = 20
PROVISIONAL_AI_MIN_LOSS_DELTA = 10

MATCH_FREQUENCY_CHOICES = [
    app_commands.Choice(name=f"{key} - {config['label']} ({config['placement_games']}판 / ±{config['placement_delta']} / ±{config['regular_delta']})", value=key)
    for key, config in MATCH_FREQUENCY_PRESETS.items()
]
TITLE_MMR_GRANDMASTER = 3200
TITLE_MMR_CHALLENGER = 3600
TITLE_MMR_ALL_ROLES_SKILLED = 3200
TITLE_MMR_BREAKTHROUGH_GAP = 1000
TITLE_MMR_COST_EFFECTIVE_GAP = 200
TITLE_MMR_UNDERDOG_GAP = 600
TITLE_MMR_SCORE_IS_EXTRA_GAP = 500
TITLE_MMR_PEAK_GAP = 1000
TITLE_MMR_TEAM_DEFICIT_GAP = 500
TITLE_MMR_FIRST_GIANT_SLAYER_GAP = 1200
TITLE_MMR_FIRST_UNDERVALUED_GAP = 100
TITLE_MMR_FIRST_TEAM_DEFICIT_GAP = 600

TITLE_LEGACY_SEASON = "S1"
TITLE_CURRENT_SEASON = "S2"
TITLE_SEASON_LABELS = {"S1": "시즌 1", "S2": "시즌 2"}
# S2 신규/개편 기록형 칭호는 이 시각 이후 경기만 집계한다.
# 기존 기록은 소급하지 않는다. (KST)
TITLE_S2_RECORD_START = datetime(2026, 8, 19, 3, 53, 0, tzinfo=KST)

TITLE_THRESHOLD_PRESETS = {
    "적음": {
        "first_50_games": 35,
        "first_all_rounder_games": 7,
        "streak_15": 11,
        "streak_20": 14,
        "all_roles_20": 15,
        "all_roles_50": 35,
        "role_master_games": 35,
        "lane_deficit_wins": 7,
        "lane_deficit_200_wins": 5,
        "team_deficit_150_wins": 4,
        "lane_deficit_games_wr": 10,
        "lane_deficit_300_wins": 4,
        "first_giant_slayer_wins": 5,
        "first_undervalued_games": 14,
        "duo_wins": 7,
        "arena_wins_3": 2,
        "arena_wins_5": 4,
        "arena_wins_10": 7,
        "aram_10_games": 7,
        "aram_10_wins": 7,
        "aram_15_games": 10,
        "aram_20_wins": 14,
        "aram_30_games": 20,
        "event_all_round_aram_wins": 7,
        "event_legend_wins": 7,
        "event_wins_20": 14,
        "event_wins_30": 21,
        "event_wins_50": 35,
        "league_wins_3": 2,
        "league_wins_5": 4,
        "league_runner_ups_3": 2,
        "league_finals_5": 4,
    },
    "보통": {
        "first_50_games": 50,
        "first_all_rounder_games": 10,
        "streak_15": 15,
        "streak_20": 20,
        "all_roles_20": 20,
        "all_roles_50": 50,
        "role_master_games": 50,
        "lane_deficit_wins": 10,
        "lane_deficit_200_wins": 7,
        "team_deficit_150_wins": 5,
        "lane_deficit_games_wr": 15,
        "lane_deficit_300_wins": 5,
        "first_giant_slayer_wins": 7,
        "first_undervalued_games": 20,
        "duo_wins": 10,
        "arena_wins_3": 3,
        "arena_wins_5": 5,
        "arena_wins_10": 10,
        "aram_10_games": 10,
        "aram_10_wins": 10,
        "aram_15_games": 15,
        "aram_20_wins": 20,
        "aram_30_games": 30,
        "event_all_round_aram_wins": 10,
        "event_legend_wins": 10,
        "event_wins_20": 20,
        "event_wins_30": 30,
        "event_wins_50": 50,
        "league_wins_3": 3,
        "league_wins_5": 5,
        "league_runner_ups_3": 3,
        "league_finals_5": 5,
    },
    "많음": {
        "first_50_games": 65,
        "first_all_rounder_games": 13,
        "streak_15": 20,
        "streak_20": 26,
        "all_roles_20": 25,
        "all_roles_50": 65,
        "role_master_games": 65,
        "lane_deficit_wins": 13,
        "lane_deficit_200_wins": 9,
        "team_deficit_150_wins": 7,
        "lane_deficit_games_wr": 20,
        "lane_deficit_300_wins": 7,
        "first_giant_slayer_wins": 9,
        "first_undervalued_games": 26,
        "duo_wins": 13,
        "arena_wins_3": 4,
        "arena_wins_5": 7,
        "arena_wins_10": 13,
        "aram_10_games": 13,
        "aram_10_wins": 13,
        "aram_15_games": 20,
        "aram_20_wins": 26,
        "aram_30_games": 40,
        "event_all_round_aram_wins": 13,
        "event_legend_wins": 13,
        "event_wins_20": 26,
        "event_wins_30": 39,
        "event_wins_50": 65,
        "league_wins_3": 4,
        "league_wins_5": 7,
        "league_runner_ups_3": 4,
        "league_finals_5": 7,
    },
}

# Render 영구 디스크가 비어 있는 첫 실행 때만, 저장소에 포함된 기존 데이터를 복사합니다.
if not os.path.exists(LUCID_FILE) and os.path.exists(LOCAL_SEED_FILE):
    shutil.copyfile(LOCAL_SEED_FILE, LUCID_FILE)

# 리그 오브 레전드 5개 포지션 정의 (출력 및 계산 순서 고정)
ROLES = rules.ROLES
PROVISIONAL_ROLE_CHOICES = [
    app_commands.Choice(name="전체 라인", value=PROVISIONAL_ALL_ROLES_VALUE),
    *[app_commands.Choice(name=role, value=role) for role in ROLES],
]
ROLE_EMOJIS = {
    "탑": "🛡️",
    "정글": "🌲",
    "미드": "⚡",
    "원딜": "🏹",
    "서폿": "💫",
}
ROLE_CUSTOM_EMOJI_NAMES = {
    "탑": "top",
    "정글": "jug",
    "미드": "mid",
    "원딜": "ad",
    "서폿": "sup",
}
CUSTOM_EMOJI_SCAN_CACHE = {}

get_lineup_weight_tier_group = rules.get_lineup_weight_tier_group
calculate_lineup_weighted_mmr = rules.calculate_lineup_weighted_mmr
get_additive_role_adjustment = rules.get_additive_role_adjustment
get_tier_rank_label = rules.get_tier_rank_label
get_tier_division = rules.get_tier_division
parse_mmr_evaluation_tier = rules.parse_mmr_evaluation_tier


def _migrate_mmr_value_v2(value):
    return rules.convert_old_mmr_to_v2(value)


def _migrate_user_record_mmr_v2(user_info):
    if not isinstance(user_info, dict):
        return 0
    changed = 0
    mmr = user_info.get("mmr")
    if isinstance(mmr, dict):
        for role, value in list(mmr.items()):
            new_value = _migrate_mmr_value_v2(value)
            if int(value or 0) != new_value:
                mmr[role] = new_value
                changed += 1
    eval_scores = user_info.get("eval_scores")
    if isinstance(eval_scores, dict):
        for role, values in list(eval_scores.items()):
            if not isinstance(values, list):
                continue
            new_values = [_migrate_mmr_value_v2(value) for value in values]
            if new_values != values:
                eval_scores[role] = new_values
                changed += len(values)
    if int(user_info.get("noban_mmr", 0) or 0) > 0:
        old = int(user_info.get("noban_mmr", 0) or 0)
        new = _migrate_mmr_value_v2(old)
        if new != old:
            user_info["noban_mmr"] = new
            changed += 1
    peaks = user_info.get("peak_records")
    if isinstance(peaks, dict) and int(peaks.get("best_mmr", 0) or 0) > 0:
        old = int(peaks.get("best_mmr", 0) or 0)
        new = _migrate_mmr_value_v2(old)
        if new != old:
            peaks["best_mmr"] = new
            changed += 1
    return changed


def _migrate_match_record_mmr_v2(record):
    if not isinstance(record, dict):
        return 0
    changed = 0
    for player in record.get("players", []) or []:
        if not isinstance(player, dict):
            continue
        for key in ("lineup_mmr", "before_mmr", "after_mmr"):
            if int(player.get(key, 0) or 0) <= 0:
                continue
            old = int(player.get(key, 0) or 0)
            new = _migrate_mmr_value_v2(old)
            if new != old:
                player[key] = new
                changed += 1
    lineup_mmr = record.get("lineup_mmr")
    if isinstance(lineup_mmr, dict):
        for uid, value in list(lineup_mmr.items()):
            if int(value or 0) <= 0:
                continue
            new = _migrate_mmr_value_v2(value)
            if int(value or 0) != new:
                lineup_mmr[uid] = new
                changed += 1
    record["rating_scale_version"] = MMR_SCALE_VERSION
    # 패치 이전 경기에는 새 AI MMR 보정을 소급 적용하지 않습니다.
    record[AI_MMR_APPLIED_KEY] = True
    record.setdefault("ai_mmr_model", "pre_v2_frozen")
    return changed


def migrate_guild_mmr_v2(guild_data):
    if not isinstance(guild_data, dict):
        return 0
    if int(guild_data.get(MMR_SCALE_VERSION_KEY, 1) or 1) >= MMR_SCALE_VERSION:
        return 0
    changed = 0
    for uid, user_info in list(guild_data.items()):
        if str(uid).startswith("_") or not isinstance(user_info, dict):
            continue
        changed += _migrate_user_record_mmr_v2(user_info)
    for record in guild_data.get(MATCH_HISTORY_KEY, []) or []:
        changed += _migrate_match_record_mmr_v2(record)
    detail_store = guild_data.get(getattr(match_stats, "DETAIL_STATS_KEY", "_match_detail_stats"), {})
    if isinstance(detail_store, dict):
        for entries in detail_store.values():
            if not isinstance(entries, dict):
                continue
            for entry in entries.values():
                if not isinstance(entry, dict):
                    continue
                for key in ("before_mmr", "opponent_mmr"):
                    if int(entry.get(key, 0) or 0) <= 0:
                        continue
                    old = int(entry.get(key, 0) or 0)
                    new = _migrate_mmr_value_v2(old)
                    if new != old:
                        entry[key] = new
                        changed += 1
    guild_data[MMR_SCALE_VERSION_KEY] = MMR_SCALE_VERSION
    return changed



# ==============================================================================
# [봇 메인 클래스 선언]
# ==============================================================================
storage.configure_runtime(lambda: globals())


class LucidBot(commands.Bot):
    def __init__(self):
        # 봇 인텐트(Intents) 활성화
        intents = discord.Intents.all()
        intents.message_content = True
        super().__init__(
            command_prefix='!', 
            intents=intents, 
            help_command=None
        )
        
        self.database_url = DATABASE_URL
        self.db_enabled = bool(self.database_url and psycopg and Jsonb)
        self.save_locks = {}
        self.save_locks_guard = threading.Lock()
        self.persistence_lock = threading.RLock()

        # 시스템 구동 시 데이터베이스를 우선 로드하고, 없으면 로컬 JSON을 시드로 사용합니다.
        self.user_data = self.load_json(LUCID_FILE)
        
        # 서버별 대기열 및 인게임 세션 관리를 위한 딕셔너리 메모리 할당
        self.queues = {} 
        self.queue_updated_at = {}
        self.queue_controller = None  # Queue MVC controller, initialized after helper aliases load.
        # Queue persistence guard: never serialize an empty/not-yet-restored runtime queue
        # over the DB snapshot during startup/reconnect.
        self.queue_restore_ready = set()
        self.queue_restore_in_progress = set()
        self.queue_restore_failed = set()
        self.active_games = {} 
        self.active_restore_ready = set()
        self.active_restore_in_progress = set()
        self.processing_games = set()
        self.processing_lineups = set()
        self.admin_operations = set()
        self.join_reservation_tasks = {}
        self.last_db_error = None
        self.last_db_error_at = None
        self.last_db_success_at = None
        self.history = {} # 경기 복구를 위한 히스토리 스냅샷 저장소
        self.ranking_refresh_loop_started = False
        self.hourly_ranking_refresh_loop_started = False
        self.queue_cleanup_loop_started = False
        self.recruitment_lineup_loop_started = False
        self.chzzk_discovery_loop_started = False
        self.coach_discord_notification_loop_started = False
        self.command_tree_synced = False
        self.chzzk_listener_tasks = {}
        self.chzzk_user_cooldowns = {}
        self.chzzk_tier_request_cache = {}
        self.chzzk_queue_locks = {}
        self.force_party_queue_locks = {}
        self.recruitment_starting_queues = set()
        self.chzzk_stats = {}
        self.slash_sync_failed_payloads = {}
        self.patch_summary_promo_pending = set()
        self.participation_panel_refresh_tasks = {}
        self.participation_panel_refresh_locks = {}
        self.party_panel_refresh_tasks = {}
        self.party_panel_refresh_locks = {}
        self.party_admin_panel_refresh_tasks = {}
        self.party_admin_panel_refresh_locks = {}
        self.party_room_action_locks = {}
        self.event_sponsor_refresh_locks = {}
        self.participation_panel_views_registered = False
        self.title_batch = None

        # 기존 수상 결과는 구 MMR 스케일 상태에서 먼저 고정한 뒤 MMR 2.0 migration을 수행합니다.
        award_snapshot_changed, frozen_awards = match_stats.freeze_existing_awards(self.user_data)
        if award_snapshot_changed:
            self.save_lucid_data()
            logger.info("기존 MVP/ACE 기록 %s경기를 이전 기준으로 고정했습니다.", frozen_awards)

        self.migrate_mmr_v2_if_needed()

        # 프로세스 종료 시점에 저장을 시도하여 데이터 유실을 최소화
        atexit.register(self.save_lucid_data)
        try:
            signal.signal(signal.SIGINT, lambda *args: self.save_lucid_data())
            signal.signal(signal.SIGTERM, lambda *args: self.save_lucid_data())
        except Exception:
            pass

    async def setup_hook(self):
        # Persistent views must be registered after the client setup starts so
        # existing panel messages keep working across process restarts.
        register_server_admin_persistent_views()

    def migrate_mmr_v2_if_needed(self):
        pending = [
            str(gid) for gid, guild_data in self.user_data.items()
            if isinstance(guild_data, dict)
            and int(guild_data.get(MMR_SCALE_VERSION_KEY, 1) or 1) < MMR_SCALE_VERSION
        ]
        if not pending:
            return False
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            backup_path = os.path.join(BACKUP_DIR, f"lucidgame_pre_mmr_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(backup_path, "w", encoding="utf-8") as fp:
                json.dump(self.user_data, fp, ensure_ascii=False, indent=2)
            logger.warning("MMR 2.0 migration pre-backup saved: %s", backup_path)
        except Exception as exc:
            logger.exception("MMR 2.0 migration backup failed; refusing to start with mixed rating scales")
            raise RuntimeError("MMR 2.0 pre-migration backup failed") from exc

        changed = 0
        for gid in pending:
            changed += migrate_guild_mmr_v2(self.user_data.get(gid, {}))
        self.save_lucid_data()
        logger.warning("MMR 2.0 migration completed: guilds=%s changed_values=%s", len(pending), changed)
        return True

    get_db_connection = storage.get_db_connection

    get_save_lock = storage.get_save_lock

    def begin_admin_operation(self, gid, operation_key):
        key = (str(gid), str(operation_key))
        if key in self.admin_operations:
            return None
        self.admin_operations.add(key)
        return key

    def finish_admin_operation(self, key):
        if key:
            self.admin_operations.discard(key)

    init_db = storage.init_db

    load_from_db = storage.load_from_db

    iter_guild_state_rows = storage.iter_guild_state_rows

    save_to_db = storage.save_to_db

    load_json_file = storage.load_json_file

    load_json = storage.load_json

    save_seed_to_db = storage.save_seed_to_db

    save_lucid_data = storage.save_lucid_data

    backup_lucid_data = storage.backup_lucid_data

LANE_ADVANTAGE_THRESHOLD = 200
HIGH_VALUE_LANE_AVG_THRESHOLD = 1800
LANE_EXCLUSION_GAP = 1300
BOT_DUO_EXCLUSION_GAP = 1300
EARLY_SERVER_MATCH_LIMIT = 20
EARLY_SERVER_LANE_EXCLUSION_GAP = 1500
HIGH_ADC_MMR_THRESHOLD = 2600
HIGH_ADC_SUPPORT_GAP = 1200
LINEUP_SYNERGY_BONUSES = {
    ("정글", "원딜"): 60,
    ("정글", "서폿"): 40,
    ("미드", "서폿"): 40,
}
LINEUP_SYNERGY_BONUS_CAP = 100
LINEUP_SYNERGY_MIN_MMR = 2400

# [규칙 2 & 3: Primary Team 결정 및 Validator 함수]
get_lane_result = rules.get_lane_result
get_primary_team = rules.get_primary_team

def is_early_match_history_server(gid):
    if gid is None:
        return False
    try:
        return len(get_valid_match_history(str(gid))) <= EARLY_SERVER_MATCH_LIMIT
    except Exception:
        return False

def get_base_lane_exclusion_gap(gid=None):
    return EARLY_SERVER_LANE_EXCLUSION_GAP if is_early_match_history_server(gid) else LANE_EXCLUSION_GAP

def get_bot_duo_exclusion_gap(gid=None):
    return EARLY_SERVER_LANE_EXCLUSION_GAP if is_early_match_history_server(gid) else BOT_DUO_EXCLUSION_GAP

def get_support_gap_limit(blue_scores, red_scores, gid=None):
    if is_early_match_history_server(gid):
        return EARLY_SERVER_LANE_EXCLUSION_GAP
    high_adc_in_lane = max(int(blue_scores[3] or 0), int(red_scores[3] or 0)) >= HIGH_ADC_MMR_THRESHOLD
    return HIGH_ADC_SUPPORT_GAP if high_adc_in_lane else LANE_EXCLUSION_GAP

def get_lane_exclusion_limit(role, blue_scores, red_scores, gid=None):
    if role == "서폿":
        return get_support_gap_limit(blue_scores, red_scores, gid)
    return get_base_lane_exclusion_gap(gid)

get_bot_duo_gap = rules.get_bot_duo_gap
get_lineup_synergy_bonuses = rules.get_lineup_synergy_bonuses

def validate_team_safety(blue_effs, red_effs, gid=None):
    lane_limits = [get_lane_exclusion_limit(role, blue_effs, red_effs, gid) for role in ROLES]
    return rules.validate_team_safety(blue_effs, red_effs, lane_limits, get_bot_duo_exclusion_gap(gid))

def validate_team(blue_effs, red_effs, blue_bot=None, red_bot=None, gid=None):
    # 1. 우위 판정 (100점 미만 무승부)
    lane_results = [get_lane_result(b, r) for b, r in zip(blue_effs, red_effs)]
    blue_wins = lane_results.count("blue")
    red_wins = lane_results.count("red")
    ties = lane_results.count("tie")

    if not validate_team_safety(blue_effs, red_effs, gid):
        return False

    # Primary Team 판정: 원딜 + (서폿 * 가중치)가 높은 팀
    primary_team = get_primary_team(blue_effs, red_effs)
    if primary_team is None:
        return False
    
    # Primary Team의 우위 라인 + 무승부 라인 포함 주도권 라인이 정확히 3개인지 확인
    if primary_team == "blue":
        return (blue_wins + ties) == 3
    return (red_wins + ties) == 3

bot = LucidBot()

# ==============================================================================
# [유틸리티 데이터 및 시스템 연산 함수]
# ==============================================================================

# 공식 내전 티어 매핑 테이블 (MMR 2.0: 메이저 400점 / 세부 100점)
TIER_DATA = {
    "챌린저 (LoL)": {
        "emoji": "🟡",
        "color": 0xf1c40f
    },
    "그랜드마스터 (LoL)": {
        "emoji": "🔴",
        "color": 0xe74c3c
    },
    "마스터 (LoL)": {
        "emoji": "🟣",
        "color": 0x9b59b6
    },
    "다이아몬드 (LoL)": {
        "emoji": "🔷",
        "color": 0x3498db
    },
    "에메랄드 (LoL)": {
        "emoji": "🟢",
        "color": 0x2ecc71
    },
    "플래티넘 (LoL)": {
        "emoji": "🔵",
        "color": 0x1abc9c
    },
    "골드 (LoL)": {
        "emoji": "🟠",
        "color": 0xe67e22
    },
    "실버 (LoL)": {
        "emoji": "⚪",
        "color": 0xbdc3c7
    },
    "브론즈 (LoL)": {
        "emoji": "🟤",
        "color": 0x95a5a6
    },
    "아이언 (LoL)": {
        "emoji": "⚫",
        "color": 0x34495e
    }
}

TIER_CUSTOM_EMOJI_LABELS = {
    "챌린저 (LoL)": "챌린저",
    "그랜드마스터 (LoL)": "그랜드마스터",
    "마스터 (LoL)": "마스터",
    "다이아몬드 (LoL)": "다이아몬드",
    "에메랄드 (LoL)": "에메랄드",
    "플래티넘 (LoL)": "플래티넘",
    "골드 (LoL)": "골드",
    "실버 (LoL)": "실버",
    "브론즈 (LoL)": "브론즈",
    "아이언 (LoL)": "아이언",
}

TIER_CUSTOM_EMOJI_KEYWORDS = {
    "챌린저 (LoL)": ("challenger",),
    "그랜드마스터 (LoL)": ("grandmaster",),
    "마스터 (LoL)": ("master",),
    "다이아몬드 (LoL)": ("diamond",),
    "에메랄드 (LoL)": ("emerald",),
    "플래티넘 (LoL)": ("platinum",),
    "골드 (LoL)": ("gold",),
    "실버 (LoL)": ("silver",),
    "브론즈 (LoL)": ("bronze",),
    "아이언 (LoL)": ("iron",),
}

LOCAL_TIER_EMOJI_FILES = [
    ("챌린저", "challenger", ("tiers", "challenger.png")),
    ("그랜드마스터", "grandmaster", ("tiers", "grandmaster.png")),
    ("마스터", "master", ("tiers", "master.png")),
    ("다이아몬드", "diamond", ("tiers", "diamond.png")),
    ("에메랄드", "emerald", ("tiers", "emerald.png")),
    ("플래티넘", "platinum", ("tiers", "platinum.png")),
    ("골드", "gold", ("tiers", "gold.png")),
    ("실버", "silver", ("tiers", "silver.png")),
    ("브론즈", "bronze", ("tiers", "bronze.png")),
    ("아이언", "iron", ("tiers", "iron.png")),
]

LOCAL_ROLE_EMOJI_FILES = [
    ("탑", "top", ("roles", "top.png")),
    ("정글", "jug", ("roles", "jungle.png")),
    ("미드", "mid", ("roles", "mid.png")),
    ("원딜", "ad", ("roles", "adc.png")),
    ("서폿", "sup", ("roles", "support.png")),
]

DEFAULT_TIER_ROLE_SPECS = [
    ("challenger", 0xf1c40f),
    ("grandmaster", 0xe74c3c),
    ("master", 0x9b59b6),
    ("diamond", 0x3498db),
    ("emerald", 0x2ecc71),
    ("platinum", 0x1abc9c),
    ("gold", 0xe67e22),
    ("silver", 0xbdc3c7),
    ("bronze", 0x95a5a6),
    ("iron", 0x34495e),
]

DEFAULT_POSITION_ROLE_SPECS = [
    ("top", 0x95a5a6),
    ("jug", 0x2ecc71),
    ("mid", 0x3498db),
    ("ad", 0xe74c3c),
    ("sup", 0xf1c40f),
]

DEFAULT_ROLE_ICON_FILES = {
    emoji_name: path_parts
    for _label, emoji_name, path_parts in LOCAL_TIER_EMOJI_FILES + LOCAL_ROLE_EMOJI_FILES
}

TIER_ROLE_ICON_FILES = {
    f"{label} (LoL)": path_parts
    for label, _emoji_name, path_parts in LOCAL_TIER_EMOJI_FILES
}

AUTO_TIER_ROLE_KEYWORDS = {
    "챌린저 (LoL)": ("challenger", "챌린저"),
    "그랜드마스터 (LoL)": ("grandmaster", "grand master", "그랜드마스터", "그마"),
    "마스터 (LoL)": ("master", "마스터"),
    "다이아몬드 (LoL)": ("diamond", "다이아몬드", "다이아"),
    "에메랄드 (LoL)": ("emerald", "에메랄드"),
    "플래티넘 (LoL)": ("platinum", "플래티넘", "플레티넘", "플래"),
    "골드 (LoL)": ("gold", "골드"),
    "실버 (LoL)": ("silver", "실버"),
    "브론즈 (LoL)": ("bronze", "브론즈"),
    "아이언 (LoL)": ("iron", "아이언"),
    "언랭": ("unrank", "unranked", "언랭", "언랭크"),
}

def get_tier_emoji(tier_name, guild=None, gid=None):
    fallback = TIER_DATA.get(tier_name, {"emoji": "❔"}).get("emoji", "❔")
    if not guild:
        return fallback
    custom_map = get_complete_tier_custom_emoji_map(guild)
    if custom_map:
        return str(custom_map.get(tier_name, fallback))
    return fallback

def get_role_display_marker(role, guild=None):
    custom_map = get_complete_role_custom_emoji_map(guild)
    if custom_map:
        return str(custom_map.get(role, role))
    return role

def normalize_custom_emoji_name(name):
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())

def normalize_role_keyword(name):
    return re.sub(r"[^a-z0-9가-힣]", "", str(name or "").lower())

def get_guild_emoji_signature(guild):
    return tuple(sorted(
        (int(getattr(emoji, "id", 0) or 0), str(getattr(emoji, "name", "") or ""))
        for emoji in getattr(guild, "emojis", []) or []
    ))

def find_tier_custom_emoji(emojis, tier_name):
    for keyword in TIER_CUSTOM_EMOJI_KEYWORDS.get(tier_name, ()):
        normalized_keyword = normalize_custom_emoji_name(keyword)
        for emoji in emojis:
            emoji_name = normalize_custom_emoji_name(getattr(emoji, "name", ""))
            if normalized_keyword == "master" and "grandmaster" in emoji_name:
                continue
            if normalized_keyword in emoji_name:
                return emoji
    return None

def get_custom_emoji_scan(guild):
    if not guild:
        return {
            "tier_map": {},
            "tier_missing": list(TIER_CUSTOM_EMOJI_KEYWORDS),
            "role_map": {},
            "role_missing": list(ROLE_CUSTOM_EMOJI_NAMES),
        }
    guild_id = int(getattr(guild, "id", 0) or 0)
    signature = get_guild_emoji_signature(guild)
    cached = CUSTOM_EMOJI_SCAN_CACHE.get(guild_id)
    if cached and cached.get("signature") == signature:
        return cached

    emojis = list(getattr(guild, "emojis", []) or [])
    tier_map = {}
    tier_missing = []
    for tier_name in TIER_CUSTOM_EMOJI_KEYWORDS:
        emoji = find_tier_custom_emoji(emojis, tier_name)
        if emoji:
            tier_map[tier_name] = emoji
        else:
            tier_missing.append(tier_name)

    role_map = {}
    role_missing = []
    for role, emoji_name in ROLE_CUSTOM_EMOJI_NAMES.items():
        emoji = next(
            (item for item in emojis if normalize_custom_emoji_name(getattr(item, "name", "")) == normalize_custom_emoji_name(emoji_name)),
            None,
        )
        if emoji:
            role_map[role] = emoji
        else:
            role_missing.append(role)

    scan = {
        "signature": signature,
        "tier_map": tier_map,
        "tier_missing": tier_missing,
        "role_map": role_map,
        "role_missing": role_missing,
    }
    CUSTOM_EMOJI_SCAN_CACHE[guild_id] = scan
    return scan

def find_auto_tier_role(guild, tier_name):
    if not guild:
        return None
    keywords = AUTO_TIER_ROLE_KEYWORDS.get(tier_name, ())
    normalized_keywords = [normalize_role_keyword(keyword) for keyword in keywords]
    for role in getattr(guild, "roles", []) or []:
        role_name = normalize_role_keyword(getattr(role, "name", ""))
        for keyword in normalized_keywords:
            if keyword in ("master", "마스터") and ("grandmaster" in role_name or "그랜드마스터" in role_name):
                continue
            if keyword and keyword in role_name:
                return role
    return None

def get_auto_tier_roles(guild):
    roles = {}
    for tier_name in AUTO_TIER_ROLE_KEYWORDS:
        role = find_auto_tier_role(guild, tier_name)
        if role:
            roles[tier_name] = role
    return roles

def can_bot_manage_role(guild, role):
    bot_member = getattr(guild, "me", None)
    permissions = getattr(bot_member, "guild_permissions", None)
    if not bot_member or not permissions or not permissions.manage_roles:
        return False
    return role < bot_member.top_role

def get_bot_role_manage_block_reason(guild, role):
    bot_member = getattr(guild, "me", None)
    permissions = getattr(bot_member, "guild_permissions", None)
    if not bot_member:
        return "봇 멤버 정보 없음"
    if not permissions or not permissions.manage_roles:
        return "봇 역할 관리 권한 없음"
    bot_top_role = getattr(bot_member, "top_role", None)
    if not bot_top_role or not role < bot_top_role:
        bot_role_name = getattr(bot_top_role, "name", "알 수 없음")
        return f"봇 최상위 역할({bot_role_name})이 대상보다 낮거나 같음"
    return "디스코드 API 거절"

def guild_supports_role_icons(guild):
    features = set(getattr(guild, "features", []) or [])
    return "ROLE_ICONS" in features

def safe_mmr_value(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def build_history_peak_mmr_map(gid):
    peaks = {}
    history = bot.user_data.get(str(gid), {}).get(MATCH_HISTORY_KEY, [])
    if not isinstance(history, list):
        return peaks
    for record in history:
        if not isinstance(record, dict) or record.get("cancelled"):
            continue
        for player in record.get("players", []) or []:
            if not isinstance(player, dict):
                continue
            uid = str(player.get("user_id") or "")
            if not uid:
                continue
            score = max(
                safe_mmr_value(player.get("before_mmr")),
                safe_mmr_value(player.get("after_mmr")),
                safe_mmr_value(player.get("lineup_mmr")),
            )
            if score <= 0:
                continue
            current = peaks.get(uid, {})
            if score > safe_mmr_value(current.get("score")):
                peaks[uid] = {"score": score, "role": player.get("role")}
    return peaks

def apply_history_peak_record(user_info, history_peak):
    if not isinstance(history_peak, dict):
        return False
    score = safe_mmr_value(history_peak.get("score"))
    if score <= 0:
        return False
    peak_records = user_info.setdefault("peak_records", {})
    if score <= safe_mmr_value(peak_records.get("best_mmr")):
        return False
    peak_records["best_mmr"] = score
    peak_records["best_mmr_role"] = history_peak.get("role") or peak_records.get("best_mmr_role")
    return True

def get_user_auto_tier_score(user_info, history_peak=None):
    user_info = ensure_user_format(user_info)
    apply_history_peak_record(user_info, history_peak)
    peak_records = user_info.get("peak_records", {})
    historical_peak = safe_mmr_value(peak_records.get("best_mmr")) if isinstance(peak_records, dict) else 0
    return max(
        get_peak_mmr(user_info.get("mmr", {})),
        get_noban_mmr(user_info),
        historical_peak,
    )

def get_user_auto_tier_name(user_info, history_peak=None):
    peak_score = get_user_auto_tier_score(user_info, history_peak)
    if peak_score <= 0:
        return "언랭"
    return get_tier_name(peak_score)

async def sync_member_tier_role(guild, gid, member, user_info, *, reason="MMR 티어 자동 동기화", history_peak=None):
    if not guild or not member:
        return {"status": "skipped", "reason": "member_missing"}
    user_info = ensure_user_format(user_info)
    target_score = get_user_auto_tier_score(user_info, history_peak)
    target_tier = "언랭" if target_score <= 0 else get_tier_name(target_score)
    tier_roles = get_auto_tier_roles(guild)
    if target_tier == "언랭":
        owned_tier_roles = [
            role for role in tier_roles.values()
            if role in getattr(member, "roles", [])
        ]
        unmanageable_roles = [role for role in owned_tier_roles if not can_bot_manage_role(guild, role)]
        if unmanageable_roles:
            return {
                "status": "unmanageable",
                "tier": target_tier,
                "score": target_score,
                "role": ", ".join(role.name for role in unmanageable_roles),
            }
        removable_roles = [
            role for role in owned_tier_roles
            if can_bot_manage_role(guild, role)
        ]
        if removable_roles:
            await member.remove_roles(*removable_roles, reason=reason)
        return {
            "status": "changed" if removable_roles else "unchanged",
            "tier": target_tier,
            "score": target_score,
            "role": "역할 제거",
            "removed": [role.name for role in removable_roles],
        }

    target_role = tier_roles.get(target_tier)
    if not target_role:
        return {"status": "missing_role", "tier": target_tier, "score": target_score}
    if not can_bot_manage_role(guild, target_role):
        return {"status": "unmanageable", "tier": target_tier, "role": target_role.name, "score": target_score}

    removable_roles = [
        role for tier, role in tier_roles.items()
        if role in getattr(member, "roles", []) and role != target_role and can_bot_manage_role(guild, role)
    ]
    changed = False
    if removable_roles:
        await member.remove_roles(*removable_roles, reason=reason)
        changed = True
    if target_role not in getattr(member, "roles", []):
        await member.add_roles(target_role, reason=reason)
        changed = True
    return {
        "status": "changed" if changed else "unchanged",
        "tier": target_tier,
        "score": target_score,
        "role": target_role.name,
        "removed": [role.name for role in removable_roles],
    }

async def sync_registered_member_tier_role(guild, gid, uid, *, reason="MMR 티어 자동 동기화", history_peak=None):
    if not guild:
        return {"status": "skipped", "reason": "guild_missing"}
    user_info = bot.user_data.get(gid, {}).get(str(uid))
    if not isinstance(user_info, dict):
        return {"status": "skipped", "reason": "user_missing"}
    member = guild.get_member(int(uid))
    if not member:
        try:
            member = await guild.fetch_member(int(uid))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
            return {"status": "skipped", "reason": "member_missing"}
    try:
        return await sync_member_tier_role(guild, gid, member, user_info, reason=reason, history_peak=history_peak)
    except discord.Forbidden:
        return {"status": "forbidden"}
    except discord.HTTPException as e:
        return {"status": "error", "reason": str(e)}

async def remove_member_auto_tier_roles(guild, member, *, reason="MMR 티어 자동 동기화"):
    if not guild or not member:
        return {"status": "skipped", "reason": "member_missing"}
    tier_roles = get_auto_tier_roles(guild)
    owned_tier_roles = [
        role for role in tier_roles.values()
        if role in getattr(member, "roles", [])
    ]
    unmanageable_roles = [role for role in owned_tier_roles if not can_bot_manage_role(guild, role)]
    if unmanageable_roles:
        return {
            "status": "unmanageable",
            "tier": "미등록",
            "score": 0,
            "role": ", ".join(role.name for role in unmanageable_roles),
        }
    removable_roles = [
        role for role in owned_tier_roles
        if can_bot_manage_role(guild, role)
    ]
    if not removable_roles:
        return {"status": "unchanged", "tier": "미등록", "score": 0, "role": "역할 없음", "removed": []}
    try:
        await member.remove_roles(*removable_roles, reason=reason)
        return {
            "status": "changed",
            "tier": "미등록",
            "score": 0,
            "role": "역할 제거",
            "removed": [role.name for role in removable_roles],
        }
    except discord.Forbidden:
        return {"status": "forbidden"}
    except discord.HTTPException as e:
        return {"status": "error", "reason": str(e)}

def get_complete_tier_custom_emoji_map(guild):
    scan = get_custom_emoji_scan(guild)
    return scan["tier_map"] if not scan["tier_missing"] else None

def get_complete_role_custom_emoji_map(guild):
    scan = get_custom_emoji_scan(guild)
    return scan["role_map"] if not scan["role_missing"] else None

def fetch_url_json(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": "LucidGameBot/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def fetch_url_bytes(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": "LucidGameBot/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()

def get_champion_data_cache(gid):
    cache = bot.user_data.setdefault(str(gid), {}).setdefault(CHAMPION_DATA_CACHE_KEY, {})
    if not isinstance(cache, dict):
        cache = {}
        bot.user_data.setdefault(str(gid), {})[CHAMPION_DATA_CACHE_KEY] = cache
    cache.setdefault("version", None)
    cache.setdefault("locale", DDRAGON_LOCALE)
    cache.setdefault("filter_version", 0)
    cache.setdefault("champions", [])
    return cache

def is_standard_lol_champion_data(champion_id, champion_name="", image_file=""):
    champion_id_key = normalize_custom_emoji_name(champion_id)
    champion_name_key = normalize_role_keyword(champion_name)
    image_key = normalize_custom_emoji_name(os.path.splitext(str(image_file or ""))[0])
    excluded_prefixes = (
        "jade",
        "classic",
        "tft",
    )
    excluded_markers = (
        "leagueclassic",
        "lolclassic",
    )
    keys = (champion_id_key, champion_name_key, image_key)
    if any(key.startswith(excluded_prefixes) for key in keys if key):
        return False
    if any(marker in key for key in keys if key for marker in excluded_markers):
        return False
    return True

async def fetch_latest_champion_data(gid, *, force=False):
    cache = get_champion_data_cache(gid)
    versions = await asyncio.to_thread(fetch_url_json, f"{DDRAGON_BASE_URL}/api/versions.json")
    latest_version = str((versions or [""])[0] or "")
    if not latest_version:
        raise RuntimeError("Data Dragon 최신 버전을 확인하지 못했습니다.")

    cached_champions = cache.get("champions")
    if (
        not force
        and cache.get("version") == latest_version
        and cache.get("filter_version") == CHAMPION_DATA_FILTER_VERSION
        and isinstance(cached_champions, list)
        and cached_champions
    ):
        return cache

    champion_url = f"{DDRAGON_BASE_URL}/cdn/{latest_version}/data/{DDRAGON_LOCALE}/champion.json"
    payload = await asyncio.to_thread(fetch_url_json, champion_url)
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    champions = []
    excluded = []
    for item in data.values():
        if not isinstance(item, dict):
            continue
        image = item.get("image", {}) if isinstance(item.get("image"), dict) else {}
        champion_id = str(item.get("id") or "").strip()
        champion_name = str(item.get("name") or champion_id).strip()
        image_file = str(image.get("full") or f"{champion_id}.png").strip()
        if not is_standard_lol_champion_data(champion_id, champion_name, image_file):
            excluded.append(champion_id or champion_name)
            continue
        if champion_id and champion_name and image_file:
            champions.append({
                "id": champion_id,
                "key": str(item.get("key") or "").strip(),
                "name": champion_name,
                "image": image_file,
            })
    champions.sort(key=lambda item: normalize_role_keyword(item.get("name")))
    cache.update({
        "version": latest_version,
        "locale": DDRAGON_LOCALE,
        "filter_version": CHAMPION_DATA_FILTER_VERSION,
        "champions": champions,
        "excluded_champions": excluded,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    bot.save_lucid_data(gid)
    return cache

def make_champion_emoji_name(champion):
    champion_id = re.sub(r"[^a-z0-9_]", "", str(champion.get("id") or "").lower())
    name = f"lol_{champion_id}" if champion_id else "lol_champion"
    if len(name) > 32:
        name = name[:32].rstrip("_")
    return name if len(name) >= 2 else "lol_champion"

def get_champion_emoji_keywords(champion):
    champion_id = str(champion.get("id") or "").strip()
    image_stem = os.path.splitext(str(champion.get("image") or ""))[0]
    raw_keywords = {
        champion_id,
        image_stem,
        str(champion.get("name") or ""),
        make_champion_emoji_name(champion),
        f"champ_{champion_id}",
        f"champion_{champion_id}",
    }
    keywords = set()
    for keyword in raw_keywords:
        custom_key = normalize_custom_emoji_name(keyword)
        role_key = normalize_role_keyword(keyword)
        if custom_key:
            keywords.add(custom_key)
        if role_key:
            keywords.add(role_key)
    return keywords

def find_champion_custom_emoji(guild, champion):
    keywords = get_champion_emoji_keywords(champion)
    for emoji in getattr(guild, "emojis", []) or []:
        emoji_names = {
            normalize_custom_emoji_name(getattr(emoji, "name", "")),
            normalize_role_keyword(getattr(emoji, "name", "")),
        }
        if keywords.intersection(name for name in emoji_names if name):
            return emoji
    return None

def get_champion_display_marker(champion_name, guild=None, gid=None):
    name = str(champion_name or "").strip()
    if not name or not guild or not gid:
        return name
    cache = get_champion_data_cache(gid)
    target = normalize_role_keyword(name)
    champion = next(
        (
            item for item in cache.get("champions", [])
            if target in {normalize_role_keyword(item.get("name")), normalize_role_keyword(item.get("id"))}
        ),
        None,
    )
    if not champion:
        return name
    emoji = find_champion_custom_emoji(guild, champion)
    return f"{emoji} {name}" if emoji else name

def get_champion_name_from_mastery_title(title):
    title = str(title or "").strip()
    if not title:
        return None
    for (champion, _games, _kind), override_title in CHAMPION_MASTERY_TITLE_OVERRIDES.items():
        if title == override_title:
            return champion
    for _games, normal_template, first_template in CHAMPION_MASTERY_TITLE_STEPS:
        champion = extract_champion_from_title_template(title, normal_template)
        if champion:
            return champion
        champion = extract_champion_from_title_template(title, first_template)
        if champion:
            return champion
    return None


def format_title_display(guild, gid, title):
    """Decorate champion-mastery titles with registered champion emoji(s)."""
    title_text = str(title or "").strip()

    multi_champions = MULTI_CHAMPION_MASTERY_TITLES.get(title_text)
    if multi_champions:
        emojis = []
        for champion in multi_champions:
            marker = get_champion_display_marker(champion, guild, gid)
            if marker != champion and marker.endswith(champion):
                emoji_text = marker[:-len(champion)].strip()
                if emoji_text and emoji_text not in emojis:
                    emojis.append(emoji_text)
        return f"{' '.join(emojis)} {title_text}".strip() if emojis else title_text

    champion = get_champion_name_from_mastery_title(title_text)
    if not champion:
        return title_text
    marker = get_champion_display_marker(champion, guild, gid)
    if marker == champion:
        return title_text
    emoji_text = marker[:-len(champion)].strip() if marker.endswith(champion) else ""
    return f"{emoji_text} {title_text}".strip() if emoji_text else title_text


def format_custom_emoji_status(guild):
    scan = get_custom_emoji_scan(guild)
    tier_missing = [TIER_CUSTOM_EMOJI_LABELS.get(tier, tier) for tier in scan["tier_missing"]]
    role_missing = scan["role_missing"]
    tier_status = "적용 가능" if not tier_missing else "미적용"
    role_status = "적용 가능" if not role_missing else "미적용"
    tier_detail = "누락 없음" if not tier_missing else "누락: " + ", ".join(tier_missing)
    role_detail = "누락 없음" if not role_missing else "누락: " + ", ".join(role_missing)
    return f"티어 이모지: **{tier_status}** ({tier_detail})\n라인 이모지: **{role_status}** ({role_detail})"

def get_public_mmr_rank(score):
    """유저 노출용 MMR 표기. 내부 계산/저장 MMR은 변경하지 않는다."""
    value = int(score or 0)
    if value <= 0:
        return "미배치"
    if value >= 3600:
        return "챌린저"
    if value >= 3200:
        return "그랜드마스터"
    if value >= 2800:
        return "마스터"
    label = str(get_tier_rank_label(value) or get_tier_name(value) or "미배치")
    return label.replace("다이아몬드", "다이아")

def format_public_mmr(score, guild=None, gid=None, *, with_emoji=True):
    value = int(score or 0)
    label = get_public_mmr_rank(value)
    if not with_emoji or value <= 0:
        return label
    return f"{get_tier_emoji(get_tier_name(value), guild, gid)} {label}"

def format_public_mmr_division_points(score, guild=None, gid=None, *, with_emoji=True):
    """전적용 압축 표기. 세부 티어는 0~99점, 마스터 이상은 2800 기준 누적 점수로 짧게 표시한다."""
    value = int(score or 0)
    if value <= 0:
        return format_public_mmr(value, guild, gid, with_emoji=with_emoji)

    tier_name = get_tier_name(value)
    emoji = f"{get_tier_emoji(tier_name, guild, gid)} " if with_emoji else ""
    if value >= 3600:
        return f"{emoji}챌린저 {value - 2800}점"
    if value >= 3200:
        return f"{emoji}그마 {value - 2800}점"
    if value >= 2800:
        return f"{emoji}마스터 {value - 2800}점"

    return f"{format_public_mmr(value, guild, gid, with_emoji=with_emoji)} {value % 100}점"

def format_profile_mmr_points(score, guild=None, gid=None, *, with_emoji=True):
    """내정보용 티어 점수 표기. 세부 티어는 0~99점, 마스터 이상은 2800 기준 누적 점수로 표시한다."""
    value = int(score or 0)
    if value <= 0:
        return format_public_mmr(value, guild, gid, with_emoji=with_emoji)

    tier_name = get_tier_name(value)
    emoji = f"{get_tier_emoji(tier_name, guild, gid)} " if with_emoji else ""
    if value >= 3600:
        return f"{emoji}챌린저 {value - 2800}점"
    if value >= 3200:
        return f"{emoji}그랜드마스터 {value - 2800}점"
    if value >= 2800:
        return f"{emoji}마스터 {value - 2800}점"
    return f"{format_public_mmr(value, guild, gid, with_emoji=with_emoji)} {value % 100}점"


def format_profile_role_score(role, score, guild, gid):
    return f"{get_role_display_marker(role, guild)} {format_profile_mmr_points(score, guild, gid)}"

def format_match_role_score(role, score, guild, gid):
    return f"{get_role_display_marker(role, guild)} {format_public_mmr(score, guild, gid)}"

def ensure_user_format(user_info):
    """
    구버전 데이터베이스 포맷을 최신 포맷으로 자동 마이그레이션 및 무결성 검증을 수행합니다.
    누락된 포지션 점수나 연승/연패 등의 딕셔너리 키를 기본값으로 안전하게 채워 넣습니다.
    """
    if 'mmr' not in user_info:
        user_info['mmr'] = {r: 0 for r in ROLES}
    elif isinstance(user_info.get('mmr'), int):
        base_mmr = user_info.get('mmr', 0)
        user_info['mmr'] = {r: base_mmr for r in ROLES}
    
    for r in ROLES:
        if r not in user_info['mmr']:
            user_info['mmr'][r] = 0
            
    if 'eval_scores' not in user_info:
        user_info['eval_scores'] = {r: [] for r in ROLES}
    elif isinstance(user_info.get('eval_scores'), list):
        user_info['eval_scores'] = {r: [] for r in ROLES}
        
    for r in ROLES:
        if r not in user_info['eval_scores']:
            user_info['eval_scores'][r] = []
            
    if 'plays' not in user_info:
        user_info['plays'] = {r: 0 for r in ROLES}
        
    for r in ROLES:
        if r not in user_info['plays']:
            user_info['plays'][r] = 0

    if 'role_stats' not in user_info or not isinstance(user_info.get('role_stats'), dict):
        user_info['role_stats'] = {r: {'win': 0, 'loss': 0} for r in ROLES}
    for r in ROLES:
        user_info['role_stats'].setdefault(r, {'win': 0, 'loss': 0})
        user_info['role_stats'][r].setdefault('win', 0)
        user_info['role_stats'][r].setdefault('loss', 0)
        user_info['role_stats'][r].setdefault('streak', 0)

    if 'duo_stats' not in user_info or not isinstance(user_info.get('duo_stats'), dict):
        user_info['duo_stats'] = {}
    for partner_uid, stats in list(user_info['duo_stats'].items()):
        if not isinstance(stats, dict):
            user_info['duo_stats'][partner_uid] = {'games': 0, 'wins': 0, 'losses': 0}
            continue
        stats.setdefault('games', 0)
        stats.setdefault('wins', 0)
        stats.setdefault('losses', 0)
    user_info.setdefault('custom_rival_uid', None)
    user_info.setdefault('rival_auto_score', 0.0)
    user_info.setdefault('rival_auto_initialized', False)
    user_info.setdefault('rival_announced_once', False)
    alt_names = user_info.get('alt_lol_names', [])
    if not isinstance(alt_names, list):
        alt_names = []
    cleaned_alt_names = []
    seen_alt_names = set()
    for name in alt_names:
        clean_name = str(name or "").strip()
        key = clean_name.lower().replace("＃", "#")
        if clean_name and key not in seen_alt_names:
            cleaned_alt_names.append(clean_name)
            seen_alt_names.add(key)
    user_info['alt_lol_names'] = cleaned_alt_names
    if 'rival_stats' not in user_info or not isinstance(user_info.get('rival_stats'), dict):
        user_info['rival_stats'] = {}
    user_info['rival_stats'].setdefault('games', 0)
    user_info['rival_stats'].setdefault('wins', 0)
    user_info['rival_stats'].setdefault('losses', 0)

    if 'underdog_stats' not in user_info or not isinstance(user_info.get('underdog_stats'), dict):
        user_info['underdog_stats'] = {}
    user_info['underdog_stats'].setdefault('lane_deficit_games', 0)
    user_info['underdog_stats'].setdefault('lane_deficit_wins', 0)
    user_info['underdog_stats'].setdefault('lane_deficit_200_wins', 0)
    user_info['underdog_stats'].setdefault('lane_deficit_300_wins', 0)
    user_info['underdog_stats'].setdefault('team_deficit_150_wins', 0)
    user_info['underdog_stats'].setdefault('lane_deficit_cost_wins', 0)
    user_info['underdog_stats'].setdefault('lane_deficit_score_games', 0)
    user_info['underdog_stats'].setdefault('lane_deficit_score_wins', 0)
    user_info['underdog_stats'].setdefault('first_giant_slayer_wins_v2', 0)
    user_info['underdog_stats'].setdefault('first_undervalued_games_v2', 0)
    user_info['underdog_stats'].setdefault('first_undervalued_wins_v2', 0)
    user_info['underdog_stats'].setdefault('first_team_deficit_wins_v2', 0)
            
    if 'win' not in user_info:
        user_info['win'] = 0
    if 'loss' not in user_info:
        user_info['loss'] = 0
        
    if 'streak' not in user_info:
        user_info['streak'] = 0

    if 'noban_mmr' not in user_info:
        user_info['noban_mmr'] = 0
    if 'noban_stats' not in user_info or not isinstance(user_info.get('noban_stats'), dict):
        user_info['noban_stats'] = {}
    user_info['noban_stats'].setdefault('win', 0)
    user_info['noban_stats'].setdefault('loss', 0)

    if 'queue_title_stats' not in user_info or not isinstance(user_info.get('queue_title_stats'), dict):
        user_info['queue_title_stats'] = {}
    user_info['queue_title_stats'].setdefault('start_count', 0)
    user_info['queue_title_stats'].setdefault('final_count', 0)

    if 'peak_records' not in user_info or not isinstance(user_info.get('peak_records'), dict):
        user_info['peak_records'] = {}
    peak_records = user_info['peak_records']
    peak_role, peak_mmr = get_peak_role_mmr(user_info.get('mmr', {}))
    peak_records.setdefault('best_streak', max(0, int(user_info.get('streak', 0) or 0)))
    peak_records.setdefault('best_mmr_role', peak_role)
    peak_records.setdefault('best_mmr', int(peak_mmr or 0))
    if peak_mmr and int(peak_mmr) > int(peak_records.get('best_mmr', 0) or 0):
        peak_records['best_mmr_role'] = peak_role
        peak_records['best_mmr'] = int(peak_mmr)

    if 'event_stats' not in user_info or not isinstance(user_info.get('event_stats'), dict):
        user_info['event_stats'] = {}
    if EVENT_MODE_KEY not in user_info['event_stats'] or not isinstance(user_info['event_stats'].get(EVENT_MODE_KEY), dict):
        user_info['event_stats'][EVENT_MODE_KEY] = {'win': 0, 'loss': 0}
    else:
        user_info['event_stats'][EVENT_MODE_KEY].setdefault('win', 0)
        user_info['event_stats'][EVENT_MODE_KEY].setdefault('loss', 0)
    if ARAM_MODE_KEY not in user_info['event_stats'] or not isinstance(user_info['event_stats'].get(ARAM_MODE_KEY), dict):
        user_info['event_stats'][ARAM_MODE_KEY] = {'win': 0, 'loss': 0}
    else:
        user_info['event_stats'][ARAM_MODE_KEY].setdefault('win', 0)
        user_info['event_stats'][ARAM_MODE_KEY].setdefault('loss', 0)

    if 'league_stats' not in user_info or not isinstance(user_info.get('league_stats'), dict):
        user_info['league_stats'] = {}
    user_info['league_stats'].setdefault('participations', 0)
    user_info['league_stats'].setdefault('wins', 0)
    user_info['league_stats'].setdefault('runner_ups', 0)
    user_info['league_stats'].setdefault('third_places', 0)
    user_info['league_stats'].setdefault('match_win', 0)
    user_info['league_stats'].setdefault('match_loss', 0)
    user_info['league_stats'].setdefault('win_streak', 0)
    user_info['league_stats'].setdefault('runner_up_streak', 0)

    if 'aram_league_stats' not in user_info or not isinstance(user_info.get('aram_league_stats'), dict):
        user_info['aram_league_stats'] = {}
    user_info['aram_league_stats'].setdefault('participations', 0)
    user_info['aram_league_stats'].setdefault('wins', 0)
    user_info['aram_league_stats'].setdefault('runner_ups', 0)
    user_info['aram_league_stats'].setdefault('third_places', 0)
    user_info['aram_league_stats'].setdefault('match_win', 0)
    user_info['aram_league_stats'].setdefault('match_loss', 0)

    if 'titles' not in user_info or not isinstance(user_info.get('titles'), dict):
        user_info['titles'] = {}
    user_info['titles'].setdefault('owned', [])
    user_info['titles'].setdefault('equipped', None)
    user_info['titles'].setdefault('pending_dynasty', None)
    user_info['titles'].setdefault('pending_custom', [])
    user_info['titles'].setdefault('achieved_custom', [])

    # 칭호 시즌 2 마이그레이션. 기존 보유/달성 기록은 시즌 1 스냅샷으로 보존한다.
    titles = user_info['titles']
    seasons = titles.setdefault('seasons', {})
    if not titles.get('_season_v2_migrated'):
        s1 = seasons.setdefault(TITLE_LEGACY_SEASON, {})
        s1.setdefault('owned', list(titles.get('owned', [])))
        s1.setdefault('achieved_custom', list(titles.get('achieved_custom', [])))
        for item in titles.get('pending_custom', []):
            if isinstance(item, dict):
                item.setdefault('season', TITLE_LEGACY_SEASON)
        titles['_season_v2_migrated'] = True
    for season_key in (TITLE_LEGACY_SEASON, TITLE_CURRENT_SEASON):
        bucket = seasons.setdefault(season_key, {})
        bucket.setdefault('owned', [])
        bucket.setdefault('achieved_custom', [])

    title_renames = {
        "👑 리그전 지배자": "👑 토너먼트 지배자",
        "💎 리그전 전설": "💎 토너먼트 전설",
    }
    title_lists = [titles.get('owned', [])]
    title_lists.extend(bucket.get('owned', []) for bucket in seasons.values() if isinstance(bucket, dict))
    for owned in title_lists:
        if not isinstance(owned, list):
            continue
        renamed = []
        for title in owned:
            title = title_renames.get(title, title)
            if title not in renamed:
                renamed.append(title)
        owned[:] = renamed
    titles['equipped'] = title_renames.get(titles.get('equipped'), titles.get('equipped'))

    return user_info

SIMULATION_UID_RANGES = (
    (990000000000000001, 990000000000000999),
    (991000000000000001, 991000000000000999),
    (992000000000000001, 992000000000000999),
)

def is_simulation_uid(uid):
    try:
        uid_int = int(uid)
    except (TypeError, ValueError):
        return False
    return any(start <= uid_int <= end for start, end in SIMULATION_UID_RANGES)

def is_simulation_user_record(uid, data):
    return bool(isinstance(data, dict) and data.get("_simulation_dummy")) or is_simulation_uid(uid)

def iter_user_records(guild_data):
    for uid, data in guild_data.items():
        if str(uid).startswith("_") or not isinstance(data, dict):
            continue
        if is_simulation_user_record(uid, data):
            continue
        yield uid, data


def should_send_patch_summary_promo(gid):
    guild_data = bot.user_data.setdefault(str(gid), {})
    if guild_data.get(PATCH_SUMMARY_PROMO_SENT_KEY):
        return False
    valid_count = sum(1 for record in guild_data.get(MATCH_HISTORY_KEY, []) if not record.get("cancelled"))
    return valid_count >= 10

def maybe_schedule_patch_summary_promo(gid):
    gid = str(gid)
    if not should_send_patch_summary_promo(gid):
        return
    if gid in getattr(bot, "patch_summary_promo_pending", set()):
        return
    bot.patch_summary_promo_pending.add(gid)
    try:
        asyncio.create_task(send_patch_summary_promo_once(gid))
    except RuntimeError:
        bot.patch_summary_promo_pending.discard(gid)
        pass

async def send_patch_summary_promo_once(gid):
    gid = str(gid)
    try:
        if not should_send_patch_summary_promo(gid):
            return

        guild_data = bot.user_data.get(gid, {})
        streaming_guide = guild_data.get(STREAMING_HELP_GUIDE_KEY)
        if not isinstance(streaming_guide, dict) or not streaming_guide.get("channel_id"):
            return

        guild = bot.get_guild(int(gid)) if str(gid).isdigit() else None
        if not guild:
            return
        channel = await get_match_output_channel(guild, gid)
        if not channel:
            return
        message = (
            "**루시드 봇 새 기능 안내**\n\n"
            "내전봇을 운영중인 서버를 위해 리그오브레전드 패치노트 요약 이미지를 준비중입니다.\n\n"
            "루시드 코칭팀이 주요 패치 내용을 이미지 한 장으로 정리해서 봇을 통해 전송해드립니다.\n\n"
            "수신을 원하시면 `/채널설정 일반 항목:패치노트`로 패치노트 채널을 설정해주세요."
        )
        try:
            await channel.send(message, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("패치요약 안내 전송 실패: guild_id=%s error=%s", gid, exc)
            return

        bot.user_data.setdefault(gid, {})[PATCH_SUMMARY_PROMO_SENT_KEY] = datetime.now(timezone.utc).isoformat()
        bot.save_lucid_data(gid)

        try:
            owner = bot.get_user(SUPPORT_DM_OWNER_ID) or await bot.fetch_user(SUPPORT_DM_OWNER_ID)
            await owner.send(
                f"[{guild.name}] 서버에서 내전이 10회 진행되었습니다",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
            logger.warning("패치요약 안내 관리자 DM 실패: guild_id=%s error=%s", gid, exc)
    finally:
        bot.patch_summary_promo_pending.discard(gid)


parse_arena_winner = rules.parse_arena_winner

parse_league_team = rules.parse_league_team

parse_league_match_no = rules.parse_league_match_no

def is_match_admin(interaction):
    permissions = getattr(interaction.user, "guild_permissions", None)
    roles = getattr(interaction.user, "roles", [])
    if bool(getattr(permissions, "administrator", False)):
        return True
    gid = str(getattr(interaction, "guild_id", "") or "")
    guild_data = bot.user_data.get(gid, {}) if gid else {}
    configured_role_id = str(guild_data.get(MATCH_ADMIN_ROLE_KEY) or "")
    if configured_role_id and any(str(getattr(role, "id", "")) == configured_role_id for role in roles):
        return True
    return any(r.name == "내전 관리자" for r in roles)

def is_bot_owner(interaction):
    return str(interaction.user.id) in BOT_OWNER_IDS

FEATURE_LABELS = {
    "league": LEAGUE_SERIES_MODE_NAME,
    "arena": "아레나(3x6)",
    "aram": "칼바람 나락 / 칼바람 리그전",
    "chzzk": "치지직 연동",
    "titles": "칭호",
}

def get_feature_flags(gid):
    guild_data = bot.user_data.setdefault(str(gid), {})
    flags = guild_data.setdefault(FEATURE_FLAGS_KEY, {})
    if not isinstance(flags, dict):
        flags = {}
        guild_data[FEATURE_FLAGS_KEY] = flags
    for key in FEATURE_LABELS:
        flags.setdefault(key, True)
    return flags

def is_feature_enabled(gid, feature_key):
    return bool(get_feature_flags(gid).get(feature_key, True))

def set_feature_enabled(gid, feature_key, enabled):
    get_feature_flags(gid)[feature_key] = bool(enabled)
    bot.save_lucid_data(gid)

def get_queue_feature_key(queue_key):
    if queue_key in (LEAGUE_QUEUE_KEY, LEAGUE_SIM_QUEUE_KEY, LEAGUE_SERIES_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY):
        return "league"
    if queue_key == ARAM_LEAGUE_QUEUE_KEY:
        return "aram"
    if queue_key == ARENA_QUEUE_NUM:
        return "arena"
    if queue_key == ARAM_QUEUE_KEY:
        return "aram"
    return None

def get_disabled_feature_message(feature_key):
    return f"⚠️ 이 서버에서는 **{FEATURE_LABELS.get(feature_key, feature_key)}** 기능이 비활성화되어 있습니다."

def is_global_announcement_enabled(gid):
    return bool(bot.user_data.setdefault(str(gid), {}).get(GLOBAL_ANNOUNCEMENT_ENABLED_KEY, True))


normalize_team_separation_pair = rules.normalize_team_separation_pair

def get_team_separation_pairs(gid):
    guild_data = bot.user_data.setdefault(str(gid), {})
    raw_pairs = guild_data.setdefault(TEAM_SEPARATION_KEY, [])
    normalized = []
    seen = set()
    for pair in raw_pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        normalized_pair = normalize_team_separation_pair(pair[0], pair[1])
        if normalized_pair[0] == normalized_pair[1]:
            continue
        pair_key = tuple(normalized_pair)
        if pair_key in seen:
            continue
        seen.add(pair_key)
        normalized.append(normalized_pair)
    if raw_pairs != normalized:
        guild_data[TEAM_SEPARATION_KEY] = normalized
    return normalized

def team_violates_separation(gid, team_uids):
    team_set = {str(uid) for uid in team_uids}
    return any(uid1 in team_set and uid2 in team_set for uid1, uid2 in get_team_separation_pairs(gid))

normalize_role_name = rules.normalize_role_name
normalize_chat_tier_code = rules.normalize_chat_tier_code
get_chat_division_mmr = rules.get_chat_division_mmr
get_chat_apex_mmr = rules.get_chat_apex_mmr
parse_chat_tier_tokens = rules.parse_chat_tier_tokens
parse_chat_tier_registration_args = rules.parse_chat_tier_registration_args
split_chzzk_plain_riot_id = rules.split_chzzk_plain_riot_id
tokenize_chzzk_plain_tier_text = rules.tokenize_chzzk_plain_tier_text
parse_chzzk_auto_tier_and_roles = rules.parse_chzzk_auto_tier_and_roles
format_chat_tier_registration = rules.format_chat_tier_registration


def is_role_mmr_assigned(user_info, role):
    user_info = ensure_user_format(user_info)
    eval_scores = user_info.get("eval_scores", {}).get(role, [])
    if eval_scores:
        return True
    return int(user_info.get("mmr", {}).get(role, 0) or 0) > 0

async def reject_duplicate_admin_operation(interaction, label):
    await interaction.response.send_message(
        f"⏳ 현재 서버에서 `{label}` 작업이 이미 처리 중입니다. 잠시 후 다시 시도해주세요.",
        ephemeral=True
    )

def make_default_user(display_name):
    return {
        'mmr': {r: 0 for r in ROLES},
        'plays': {r: 0 for r in ROLES},
        'eval_scores': {r: [] for r in ROLES},
        'win': 0,
        'loss': 0,
        'streak': 0,
        'noban_mmr': 0,
        'noban_stats': {'win': 0, 'loss': 0},
        'queue_title_stats': {'start_count': 0, 'final_count': 0},
        'rival_stats': {'games': 0, 'wins': 0, 'losses': 0},
        'peak_records': {'best_streak': 0, 'best_mmr_role': None, 'best_mmr': 0},
        'alt_lol_names': [],
        'lol_name': display_name
    }

FIRST_TITLE_DEFS = {
    "inaugural_champion": {
        "title": "👑 초대 챔피언",
        "condition": f"{LEAGUE_TITLE_NAME} 1회차 우승팀 소속"
    },
    "first_50_games": {
        "title": "⚔️ 첫 번째 선봉장",
        "condition": "내전 50판을 가장 먼저 달성"
    },
    "first_all_lane_challenger": {
        "title": "🌌 내가 하늘에 서겠다",
        "condition": "모든 라인 배치 완료 + 서버 최초 종합 평균 MMR 챌린저 티어 달성"
    },
    "first_top_challenger": {
        "title": "🏔️ 고독한 개척자",
        "condition": "서버 최초 탑 MMR 챌린저 티어 달성"
    },
    "first_jungle_challenger": {
        "title": "🧠 최초의 설계자",
        "condition": "서버 최초 정글 MMR 챌린저 티어 달성"
    },
    "first_mid_challenger": {
        "title": "🌟 중앙의 선구자",
        "condition": "서버 최초 미드 MMR 챌린저 티어 달성"
    },
    "first_adc_challenger": {
        "title": "🎯 승부의 결정자",
        "condition": "서버 최초 원딜 MMR 챌린저 티어 달성"
    },
    "first_support_challenger": {
        "title": "🤝 모두의 조력자",
        "condition": "서버 최초 서폿 MMR 챌린저 티어 달성"
    },
    "first_all_rounder": {
        "title": "🌪️ 전장의 만능패",
        "condition": "서버 최초 모든 라인 10판 이상 달성"
    },
    "first_arena_champion": {
        "title": "🏟️ 아레나 초대 챔피언",
        "condition": "서버 최초 아레나 우승"
    },
    "first_threepeat": {
        "title": "🥇 전무후무한 쓰리핏",
        "condition": f"서버 최초 {LEAGUE_TITLE_NAME} 3회 연속 우승"
    },
    "first_aram_10_games": {
        "title": "🌪️ 칼바람 개시자",
        "condition": "서버 최초 칼바람 나락 10판 참가"
    },
    "first_aram_10_wins": {
        "title": "❄️ 첫눈 위의 승자",
        "condition": "서버 최초 칼바람 나락 10승"
    },
    "first_aram_high_winrate": {
        "title": "🎲 운 좋은 사람 아님",
        "condition": "서버 최초 칼바람 나락 10판 이상 + 승률 70% 이상"
    },
    "first_double_crown": {
        "title": "⚔️ 두 전장의 개척자",
        "condition": f"서버 최초 {LEAGUE_TITLE_NAME} 우승 1회 이상 + 아레나 우승 1회 이상"
    },
    "first_giant_slayer": {
        "title": "🗡️ 최초의 거인 학살자",
        "condition": f"본인보다 맞라인 MMR이 {TITLE_MMR_FIRST_GIANT_SLAYER_GAP}점 이상 높은 상대를 상대로 7회 승리"
    },
    "first_undervalued_icon": {
        "title": "💎 저평가의 아이콘",
        "condition": f"맞라인 MMR {TITLE_MMR_FIRST_UNDERVALUED_GAP}점 이상 열세 경기 20전 이상 + 승률 60% 이상 서버 최초 달성"
    },
    "first_disadvantage_carry": {
        "title": "🔥 포기하면 그순간이 시합 종료",
        "condition": f"팀 평균 MMR이 {TITLE_MMR_FIRST_TEAM_DEFICIT_GAP}점 이상 낮은 경기에서 5회 승리"
    },
    "first_low_tier_3_wins": {
        "title": "🌿 첫 새싹",
        "condition": "서버 최초 저티어 큐 3승"
    },
    "first_mvp_10": {
        "title": "👑 괜찮아, 난 최강이니까",
        "condition": "서버 최초 상세스탯 MVP 10회 달성"
    },
    "first_ace_10": {
        "title": "🛡️ 패배로 가리지 못한",
        "condition": "서버 최초 상세스탯 ACE 10회 달성"
    },
    "first_award_30": {
        "title": "👑 너무 강한 말은 쓰지 마",
        "condition": "시즌 2 MVP 포인트 2000pt 서버 최초 달성"
    },
    "first_streak_10": {
        "title": "계획대로",
        "condition": "서버 최초 일반 내전 10연승 달성"
    },
    "first_breakthrough_500": {
        "title": "한계돌파",
        "condition": f"첫 배치 점수보다 한 라인 MMR을 {TITLE_MMR_BREAKTHROUGH_GAP}점 이상 올린 서버 최초 유저"
    },
    "first_zero_death_win_streak_2": {
        "title": "🛡️ 살아남는 자가 강한 것",
        "condition": "서버 최초 상세스탯 기준 2판 연속 0데스 승리"
    },
    "first_zero_death_loss": {
        "title": "🕯️ 사람이 언제 죽는다 생각하나",
        "condition": "서버 최초 상세스탯 기준 0데스 패배"
    },
    "first_seven_down_eight_up": {
        "title": "칠전팔기",
        "condition": "서버 최초 일반 내전 7연패 이후 8연승 달성"
    },
    "first_rival_match": {
        "title": "⚔️ 운명의 대진",
        "condition": "서버 최초 대표 라이벌 성립 후 재대결(누적 8번째 맞대결) 성사"
    },
    "first_rival_win": {
        "title": "🔥 이름을 건 승부",
        "condition": "서버 최초 대표 라이벌 맞대결 6승 달성"
    },
    "first_rival_10_even": {
        "title": "⚖️ 끝나지 않은 승부",
        "condition": "서버 최초 대표 라이벌 맞대결 정확히 10판 5승 5패 달성"
    },
    "first_penta_kill": {
        "title": "🌟 최초의 펜타킬",
        "condition": "서버 최초 ROFL 상세스탯 기준 펜타킬 달성"
    },
    "first_ai_120": {
        "title": "👁️ 서버가 목격한 것",
        "condition": "서버 최초 단일 경기 AI Score 120점 이상 달성"
    },
}

GENERAL_TITLE_DEFS = {
    "perfect_start": "📋 완벽한 출발",
    "grandmaster": "🔴 그랜드마스터의 위엄",
    "challenger": "🟡 챌린저의 별",
    "streak_15": "🔥 전장의 폭주자",
    "streak_20": "🌋 꺼지지 않는 불꽃",
    "league_wins_3": "👑 토너먼트 지배자",
    "league_wins_5": "💎 토너먼트 전설",
    "league_runner_ups_3": "🥈 결승의 증명",
    "league_finals_5": "⚔️ 결승 단골손님",
    "league_runner_up_streak_2": "🥈 2등도 잘한거야!",
    "league_final_mvp_1": "🌟 왕좌의 별",
    "league_final_mvp_3": "👑 결승을 지배한 자",
    "league_final_ace_1": "🔥 끝까지 증명한 자",
    "league_final_ace_3": "🛡️ 마지막 문턱의 수문장",
    "arena_wins_3": "🏟️ 아레나 지배자",
    "arena_wins_5": "🎪 아레나의 왕",
    "arena_wins_10": "🛡️ 최후의 생존자",
    "aram_games_15": "🎲 주사위 중독자",
    "aram_wins_10": "❄️ 눈싸움 장인",
    "aram_games_30": "🌪️ 칼바람 단골손님",
    "aram_wins_20": "🧊 얼음길 산책자",
    "aram_high_winrate": "🔥 이상하게 잘함",
    "event_double_crown": "🏆 더블 크라운",
    "event_all_round_player": "🌌 전장의 올라운더",
    "event_wins_20": "⚔️ 어디서든 이기는 사람",
    "event_wins_30": "🏆 이기는게 제일 쉬웠어요",
    "event_wins_50": "🌌 전장의 지배자",
    "all_roles_20": "🧩 만능 기사",
    "all_roles_50": "🌈 다섯 길을 걷는 자",
    "all_roles_20_master": "🌌 다섯 길의 숙련자",
    "cost_effective_model": "💰 가성비의 표본",
    "underdog_hunter": "🐺 언더독 헌터",
    "disadvantage_taste": "🔥 불리해야 제맛",
    "score_is_extra": "🎲 점수는 거들 뿐",
    "peak_confiscator": "⛓️ 고점 압수",
    "low_tier_5_games": "🌱 새싹 소환사",
    "low_tier_3_games_2_wins": "🌤️ 햇살 받은 새싹",
    "low_tier_5_games_70_wr": "✨ 떠오르는 신성",
    "low_tier_10_games": "🎮 저랑 게임해요 !",
    "low_tier_10_games_65_wr": "🌟 기대되는 유망주",
    "low_tier_3_streak": "🔥 떠오르는 태양",
    "loss_streak_7": "🧍 도망치면안돼",
    "queue_start_5": "⚔️ 전장의 개막자",
    "queue_start_15": "🚩 심장을바쳐라",
    "queue_final_5": "🧩 마지막 한 조각",
    "queue_final_15": "🔥 점화의 마침표",
    "mvp_10": "✨ 환호가 향한",
    "ace_10": "🕯️ 난 절대 포기하지않아",
    "award_20": "🎭 무대의 중심",
    "rival_matches_7": "⚔️ 숙명의 상대",
    "penta_1": "펜타킬러",
    "penta_3": "펜타 사냥꾼",
    "penta_5": "펜타킬 마스터",
    "penta_10": "펜타펜타펜타펜타펜타",
    "objective_steal_1": "🐉 용 도둑",
    "baron_steal_1": "🟣 바론 강탈자",
    "baron_steal_3": "👑 이거 내 바론인데 ?",
    "baron_steal_5": "🟣 작전명 왕호야!",
    "dragon_steal_3": "🐲 용은 자연의 것",
    "dragon_steal_10": "🐉 용의 천적",
    "server_admin": "🛡️ 서버 관리자",
    "match_admin": "⚔️ 내전 관리자",
    "ai_120": "💥 인간 하이라이트",
    "ai_130": "🌠 점수판 파괴자",
    "ai_recent5_avg100": "🔥 폼 미쳤다",
    "ai_recent10_avg100": "🌌 천외천(天外天)",
    "ai_two_110_same_day": "🎯 완벽한 하루",
    "weekly_mvp_twice": "🥇 무대 독점",
    "clean_game": "🧹 클린 게임",
    "kills_15_win": "⚔️ 학살 개시",
    "kp_80_win": "🤝 전장 지휘관",
    "gpm_lane_100_win": "💰 돈이 곧 힘이다",
    "daily_mvp_2": "🌙 오늘은 내가 캐리머신",
    "underdog_ai_110": "🎲 역배의 신",
    "lane_gap_mvp_600": "🧨 판을 뒤집은 사람",
    "showmaker_challenge": "ShowMaker 챌린지",
}

GENERAL_TITLE_CONDITIONS = {
    "perfect_start": "한 라인 배치 7승 0패 달성",
    "grandmaster": "모든 라인 배치 완료 + 종합 평균 MMR 그랜드마스터 티어 달성",
    "challenger": "모든 라인 배치 완료 + 종합 평균 MMR 챌린저 티어 달성",
    "streak_15": "일반 내전 연승 기준 달성",
    "streak_20": "일반 내전 고연승 기준 달성",
    "league_wins_3": f"{LEAGUE_TITLE_NAME} 우승 기준 달성",
    "league_wins_5": f"{LEAGUE_TITLE_NAME} 고우승 기준 달성",
    "league_runner_ups_3": f"{LEAGUE_TITLE_NAME} 준우승 기준 달성",
    "league_finals_5": f"{LEAGUE_TITLE_NAME} 결승 진출 기준 달성",
    "league_runner_up_streak_2": f"{LEAGUE_TITLE_NAME} 2회 연속 준우승 달성",
    "league_final_mvp_1": f"{LEAGUE_TITLE_NAME} 결승전 MVP 1회 달성",
    "league_final_mvp_3": f"{LEAGUE_TITLE_NAME} 결승전 MVP 3회 달성",
    "league_final_ace_1": f"{LEAGUE_TITLE_NAME} 결승전 ACE 1회 달성",
    "league_final_ace_3": f"{LEAGUE_TITLE_NAME} 결승전 ACE 3회 달성",
    "arena_wins_3": "아레나 우승 기준 달성",
    "arena_wins_5": "아레나 고우승 기준 달성",
    "arena_wins_10": "아레나 최상위 우승 기준 달성",
    "aram_games_15": "칼바람 나락 참가 판수 기준 달성",
    "aram_wins_10": "칼바람 나락 승리 기준 달성",
    "aram_games_30": "칼바람 나락 고참가 판수 기준 달성",
    "aram_wins_20": "칼바람 나락 고승리 기준 달성",
    "aram_high_winrate": "칼바람 나락 참가 판수 기준 + 승률 70% 이상",
    "event_double_crown": f"{LEAGUE_TITLE_NAME} 우승 1회 이상 + 아레나 우승 1회 이상",
    "event_all_round_player": f"{LEAGUE_TITLE_NAME}/아레나 우승 경험 + 칼바람 나락 승리 기준 달성",
    "event_wins_20": "이벤트 모드 통합 승리 기준 달성",
    "event_wins_30": "이벤트 모드 통합 고승리 기준 달성",
    "event_wins_50": "이벤트 모드 통합 최상위 승리 기준 달성",
    "all_roles_20": "모든 라인 판수 기준 달성",
    "all_roles_50": "모든 라인 고판수 기준 달성",
    "all_roles_20_master": f"모든 라인 판수 기준 달성 + 종합 평균 MMR {TITLE_MMR_ALL_ROLES_SKILLED}점 이상",
    "cost_effective_model": "라인 MMR 열세 경기 승리 기준 달성",
    "underdog_hunter": f"라인 MMR {TITLE_MMR_UNDERDOG_GAP}점 이상 열세 경기 승리 기준 달성",
    "disadvantage_taste": f"팀 평균 MMR {TITLE_MMR_TEAM_DEFICIT_GAP}점 이상 열세 경기 승리 기준 달성",
    "score_is_extra": "라인 MMR 열세 경기 판수 기준 + 승률 60% 이상",
    "peak_confiscator": f"라인 MMR {TITLE_MMR_PEAK_GAP}점 이상 열세 경기 승리 기준 달성",
    "low_tier_5_games": "저티어 큐 참가 5판 달성",
    "low_tier_3_games_2_wins": "저티어 큐 5판 이상 + 3승 이상",
    "low_tier_5_games_70_wr": "저티어 큐 5판 이상 + 승률 70% 이상",
    "low_tier_10_games": "저티어 큐 참가 10판 달성",
    "low_tier_10_games_65_wr": "저티어 큐 10판 이상 + 승률 65% 이상",
    "low_tier_3_streak": "저티어 큐 4연승 달성",
    "loss_streak_7": "일반 내전 7연패 이상 달성",
    "queue_start_5": "10인 대기열 0/10에서 첫 참가 10회",
    "queue_start_15": "10인 대기열 0/10에서 첫 참가 30회",
    "queue_final_5": "10인 대기열 9/10에서 마지막 참가 10회",
    "queue_final_15": "10인 대기열 9/10에서 마지막 참가 30회",
    "mvp_10": "상세스탯 MVP 10회 달성",
    "ace_10": "상세스탯 ACE 10회 달성",
    "award_20": "시즌 2 MVP 포인트 1000pt 달성",
    "rival_matches_7": "대표 라이벌과 상대팀으로 12회 매치 성사",
    "penta_1": "ROFL 상세스탯 기준 펜타킬 1회 달성",
    "penta_3": "ROFL 상세스탯 기준 펜타킬 3회 달성",
    "penta_5": "ROFL 상세스탯 기준 펜타킬 5회 달성",
    "penta_10": "ROFL 상세스탯 기준 펜타킬 10회 달성",
    "objective_steal_1": "한 경기에서 Riot OBJECTIVES_STOLEN 1회 이상 달성",
    "baron_steal_1": "확정 판정 바론 스틸 1회 달성",
    "baron_steal_3": "확정 판정 바론 스틸 누적 3회 달성",
    "baron_steal_5": "확정 판정 바론 스틸 누적 5회 달성",
    "dragon_steal_3": "확정 판정 용 스틸 누적 3회 달성",
    "dragon_steal_10": "확정 판정 용 스틸 누적 10회 달성",
    "server_admin": "Discord 서버 관리자 권한 보유",
    "match_admin": "LucidGame 내전 관리자 권한 보유",
    "ai_120": "단일 경기 AI Score 120점 이상",
    "ai_130": "단일 경기 AI Score 130점 이상",
    "ai_recent5_avg100": "최근 ROFL 상세기록 5경기 평균 AI Score 100점 이상",
    "ai_recent10_avg100": "최근 ROFL 상세기록 10경기 평균 AI Score 100점 이상",
    "ai_two_110_same_day": "같은 날 연속 2경기 AI Score 110점 이상",
    "weekly_mvp_twice": "주간 MVP 포인트 랭킹 2주 연속 1위",
    "clean_game": "승리 경기 0데스 + AI Score 100점 이상",
    "kills_15_win": "한 경기 15킬 이상 + 승리",
    "kp_80_win": "한 경기 킬 관여율 80% 이상 + K+A 10 이상 + 승리",
    "gpm_lane_100_win": "20분 이상 경기에서 동일 포지션 상대보다 GPM 180 이상 우위 + 승리",
    "daily_mvp_2": "같은 날 MVP 3회 달성",
    "underdog_ai_110": "팀 평균 MMR 300점 이상 열세에서 AI Score 110점 이상 + 승리",
    "lane_gap_mvp_600": "상대 라인 MMR 600점 이상 열세에서 MVP 획득",
    "showmaker_challenge": "시즌 2에서 서로 다른 챔피언 80종 이상 플레이",
}


















def format_lineup_player_line(role, user, user_info, tier_emoji, score):
    equipped_title = format_lineup_title_badge(user_info)
    name_part = f"{equipped_title} {user.mention}" if equipped_title else user.mention
    return f"{get_role_display_marker(role, getattr(user, 'guild', None))} {name_part}\n`{score}점` {tier_emoji}"

def get_lineup_display_name(guild, gid, user_or_uid):
    if hasattr(user_or_uid, "display_name"):
        return discord.utils.escape_markdown(str(user_or_uid.display_name))
    uid = str(user_or_uid)
    member = guild.get_member(int(uid)) if guild else None
    if member:
        return discord.utils.escape_markdown(str(member.display_name))
    return discord.utils.escape_markdown(get_saved_lol_name(gid, uid, f"UID {uid}"))

def get_lineup_member_text(guild, gid, user_or_uid):
    """Lineup UI uses the registered Riot name, not a Discord mention.

    Mentions can render as raw numeric IDs on some mobile clients. Match
    notifications are delivered separately, so lineup embeds stay readable.
    """
    uid = get_lineup_user_id(user_or_uid)
    fallback = get_lineup_display_name(guild, gid, user_or_uid)
    riot_name = compact_riot_name(get_saved_lol_name(gid, uid, fallback))
    return discord.utils.escape_markdown(riot_name or fallback)

def get_lineup_user_id(user_or_uid):
    return str(user_or_uid.id) if hasattr(user_or_uid, "id") else str(user_or_uid)

def get_lineup_title_text(user_info):
    title = format_lineup_title_badge(user_info)
    return title if title else "-"

def format_lineup_title_or_space(title):
    return title if title and title != "-" else "\u200b"

def format_lineup_gap_text(gap, blue_label="BLUE", red_label="RED", use_icons=True):
    gap = int(gap or 0)
    blue_prefix = f"🔵 {blue_label}" if use_icons else blue_label
    red_prefix = f"🔴 {red_label}" if use_icons else red_label

    if abs(gap) < LANE_ADVANTAGE_THRESHOLD:
        if gap > 0:
            return f"⚪ 동률권 ({blue_label} +{gap})"
        if gap < 0:
            return f"⚪ 동률권 ({red_label} +{abs(gap)})"
        return "⚪ 동률권"

    if gap > 0:
        return f"{blue_prefix} +{gap}"
    return f"{red_prefix} +{abs(gap)}"

def format_lineup_lane_score_text(blue_score, red_score, gap_text, guild=None, gid=None):
    blue_score = int(blue_score or 0)
    red_score = int(red_score or 0)
    gap = blue_score - red_score
    if gap > 0:
        advantage = f"🔵 B+{gap}"
    elif gap < 0:
        advantage = f"🔴 R+{abs(gap)}"
    else:
        advantage = "동률"

    # 서버에 티어 커스텀 이모지가 완비된 경우에는 라인별 우세를 이모지만으로 압축한다.
    custom_map = get_complete_tier_custom_emoji_map(guild) if guild else None
    if custom_map:
        blue_tier = get_tier_name(blue_score)
        red_tier = get_tier_name(red_score)
        blue_icon = str(custom_map.get(blue_tier, ""))
        red_icon = str(custom_map.get(red_tier, ""))
        if blue_icon and red_icon:
            return f"{blue_icon} **VS** {red_icon} {advantage}"

    return f"`{get_public_mmr_rank(blue_score)} VS {get_public_mmr_rank(red_score)}` {advantage}"

def format_lineup_matchup_block(guild, gid, role, blue_user, blue_info, blue_score, red_user, red_info, red_score):
    blue_title = get_lineup_title_text(blue_info)
    red_title = get_lineup_title_text(red_info)
    blue_name = get_lineup_member_text(guild, gid, blue_user)
    red_name = get_lineup_member_text(guild, gid, red_user)
    gap = int(blue_score or 0) - int(red_score or 0)
    gap_text = format_lineup_gap_text(gap, use_icons=False)
    return (
        f"**[BLUE]** 🔵 {blue_title}　　**[RED]** 🔴 {red_title}\n"
        f"**[{role}]** 🔵 {blue_name} `{get_public_mmr_rank(blue_score)}` vs 🔴 {red_name} `{get_public_mmr_rank(red_score)}` · **{gap_text}**"
    )

def build_classic_lineup_columns(guild, gid, blue_team, red_team, title_overrides=None):
    title_overrides = title_overrides or {}
    blue_lines = []
    mid_lines = []
    red_lines = []
    lane_gap_lines = []
    for i, role in enumerate(ROLES):
        blue_user, _blue_role, _blue_eff, blue_mmr = blue_team[i]
        red_user, _red_role, _red_eff, red_mmr = red_team[i]
        blue_uid = get_lineup_user_id(blue_user)
        red_uid = get_lineup_user_id(red_user)
        blue_info = ensure_user_format(bot.user_data.get(gid, {}).get(blue_uid, make_default_user(get_lineup_display_name(guild, gid, blue_user))))
        red_info = ensure_user_format(bot.user_data.get(gid, {}).get(red_uid, make_default_user(get_lineup_display_name(guild, gid, red_user))))
        blue_title = title_overrides.get(blue_uid)
        red_title = title_overrides.get(red_uid)
        blue_title = blue_title if blue_title is not None else get_lineup_title_text(blue_info)
        red_title = red_title if red_title is not None else get_lineup_title_text(red_info)
        blue_title = format_lineup_title_or_space(blue_title)
        red_title = format_lineup_title_or_space(red_title)
        blue_name = get_lineup_member_text(guild, gid, blue_user)
        red_name = get_lineup_member_text(guild, gid, red_user)
        blue_tier_emoji = get_tier_emoji(get_tier_name(int(blue_mmr or 0)), guild, gid)
        red_tier_emoji = get_tier_emoji(get_tier_name(int(red_mmr or 0)), guild, gid)
        gap = int(blue_mmr or 0) - int(red_mmr or 0)
        gap_text = format_lineup_gap_text(gap)

        blue_lines.append(f"{blue_title}\n{get_role_display_marker(role, guild)} {blue_name}")
        mid_lines.append(f"\u200b\n{blue_tier_emoji}　**VS**　{red_tier_emoji}")
        red_lines.append(f"{red_title}\n{red_name}")
        lane_gap_lines.append(f"{get_role_display_marker(role, guild)} {format_lineup_lane_score_text(blue_mmr, red_mmr, gap_text, guild, gid)}")

    return "\n\n".join(blue_lines), "\n\n".join(mid_lines), "\n\n".join(red_lines), "\n".join(lane_gap_lines)

def build_classic_lineup_blocks(guild, gid, blue_team, red_team):
    blocks = []
    lane_gap_lines = []
    for i, role in enumerate(ROLES):
        blue_user, _blue_role, _blue_eff, blue_mmr = blue_team[i]
        red_user, _red_role, _red_eff, red_mmr = red_team[i]
        blue_uid = get_lineup_user_id(blue_user)
        red_uid = get_lineup_user_id(red_user)
        blue_info = ensure_user_format(bot.user_data.get(gid, {}).get(blue_uid, make_default_user(get_lineup_display_name(guild, gid, blue_user))))
        red_info = ensure_user_format(bot.user_data.get(gid, {}).get(red_uid, make_default_user(get_lineup_display_name(guild, gid, red_user))))
        blue_title = get_lineup_title_text(blue_info)
        red_title = get_lineup_title_text(red_info)
        blue_name = get_lineup_member_text(guild, gid, blue_user)
        red_name = get_lineup_member_text(guild, gid, red_user)
        gap = int(blue_mmr or 0) - int(red_mmr or 0)
        gap_text = format_lineup_gap_text(gap)

        blocks.append(
            f"{get_role_display_marker(role, guild)}  🔵 {blue_title}  /  🔴 {red_title}\n"
            f"🔵 {blue_name} `{get_public_mmr_rank(blue_mmr)}`  vs  🔴 {red_name} `{get_public_mmr_rank(red_mmr)}`"
        )
        lane_gap_lines.append(f"{get_role_display_marker(role, guild)} {gap_text}")
    return "\n\n".join(blocks), "\n".join(lane_gap_lines)

def build_classic_vertical_lineup_sections(guild, gid, blue_team, red_team, title_overrides=None):
    title_overrides = title_overrides or {}
    blue_lines = []
    red_lines = []
    lane_gap_lines = []

    for i, role in enumerate(ROLES):
        blue_user, _blue_role, _blue_eff, blue_mmr = blue_team[i]
        red_user, _red_role, _red_eff, red_mmr = red_team[i]
        blue_uid = get_lineup_user_id(blue_user)
        red_uid = get_lineup_user_id(red_user)
        blue_info = ensure_user_format(bot.user_data.get(gid, {}).get(blue_uid, make_default_user(get_lineup_display_name(guild, gid, blue_user))))
        red_info = ensure_user_format(bot.user_data.get(gid, {}).get(red_uid, make_default_user(get_lineup_display_name(guild, gid, red_user))))

        blue_title = title_overrides.get(blue_uid)
        red_title = title_overrides.get(red_uid)
        blue_title = blue_title if blue_title is not None else get_lineup_title_text(blue_info)
        red_title = red_title if red_title is not None else get_lineup_title_text(red_info)
        blue_title = "" if not blue_title or blue_title == "-" else f" `{blue_title}`"
        red_title = "" if not red_title or red_title == "-" else f" `{red_title}`"

        blue_name = get_lineup_member_text(guild, gid, blue_user)
        red_name = get_lineup_member_text(guild, gid, red_user)
        blue_tier_emoji = get_tier_emoji(get_tier_name(int(blue_mmr or 0)), guild, gid)
        red_tier_emoji = get_tier_emoji(get_tier_name(int(red_mmr or 0)), guild, gid)
        gap = int(blue_mmr or 0) - int(red_mmr or 0)
        gap_text = format_lineup_gap_text(gap)

        blue_lines.append(f"{get_role_display_marker(role, guild)} {blue_name} `{get_public_mmr_rank(blue_mmr)}` {blue_tier_emoji}{blue_title}")
        red_lines.append(f"{get_role_display_marker(role, guild)} {red_name} `{get_public_mmr_rank(red_mmr)}` {red_tier_emoji}{red_title}")
        lane_gap_lines.append(f"{get_role_display_marker(role, guild)} {format_lineup_lane_score_text(blue_mmr, red_mmr, gap_text, guild, gid)}")

    return "\n".join(blue_lines), "\n".join(red_lines), "\n".join(lane_gap_lines)

def build_classic_power_summary_embed(guild, gid, queue_key, blue_team, red_team, *, test_mode=False):
    blue_total = sum(int(item[3] or 0) for item in blue_team)
    red_total = sum(int(item[3] or 0) for item in red_team)
    blue_avg = int(blue_total / len(blue_team)) if blue_team else 0
    red_avg = int(red_total / len(red_team)) if red_team else 0
    avg_diff = blue_avg - red_avg

    if abs(avg_diff) <= 50:
        gauge_str = "🔹 [█████⚖️█████] 🔹\n✨ 분석 결과: 완벽한 매치업! ✨"
    elif avg_diff > 0:
        if avg_diff > 360:
            gauge_str = "🔵 [████████░░] 🔴\n⚠️ 전력 경고: 블루팀이 매우 우세합니다."
        elif avg_diff > 160:
            gauge_str = "🔵 [███████░░░] 🔴\n⚖️ 전력 분석: 블루팀이 우세하지만, 충분히 뒤집을 수 있습니다."
        else:
            gauge_str = "🔵 [██████░░░░] 🔴\n⚖️ 전력 분석: 블루팀이 살짝 앞서지만 적당한 차이입니다."
    else:
        if avg_diff < -360:
            gauge_str = "🔵 [░░████████] 🔴\n⚠️ 전력 경고: 레드팀이 매우 우세합니다."
        elif avg_diff < -160:
            gauge_str = "🔵 [░░░███████] 🔴\n⚖️ 전력 분석: 레드팀이 우세하지만, 충분히 뒤집을 수 있습니다."
        else:
            gauge_str = "🔵 [░░░░██████] 🔴\n⚖️ 전력 분석: 레드팀이 살짝 앞서지만 적당한 차이입니다."

    if abs(avg_diff) > 360 and blue_team and red_team:
        worst_pos = None
        max_gap = 0
        for i, pos in enumerate(ROLES):
            gap = abs(int(blue_team[i][3] or 0) - int(red_team[i][3] or 0))
            if gap > max_gap:
                max_gap = gap
                worst_pos = pos
        gauge_str += (
            f"\n\n🚨 **[AI 밸런스 경고]** 🚨\n"
            f"팀 평균 격차: **{abs(avg_diff)}점**\n"
            f"가장 큰 라인 격차: **{worst_pos} {max_gap}점**\n\n"
            f"💡 **포지션 조정 추천**\n"
            f"- **{worst_pos}** 라인 점수대가 한쪽으로 몰려 있습니다.\n"
            f"- 비슷한 점수대 유저가 다음 신청 때 **{worst_pos}**도 열어주면 매칭 폭이 넓어집니다.\n"
        )

    title_prefix = "🧪 포맷 테스트 · " if test_mode else ""
    embed = discord.Embed(
        title=f"⚔️ {title_prefix}{get_queue_label(queue_key)} 큐 매치 라인업",
        description=f"**📊 양 팀 전력 비교**\n{gauge_str}",
        color=0x2b2d31,
    )
    embed.add_field(name="🔵 BLUE 평균", value=f"**{get_public_mmr_rank(blue_avg)}**", inline=True)
    embed.add_field(name="🔴 RED 평균", value=f"**{get_public_mmr_rank(red_avg)}**", inline=True)
    if test_mode:
        embed.set_footer(text="테스트 출력입니다. 팀 재계산/음성 이동은 실행하지 않습니다.")
    return embed

def apply_classic_lineup_embed(embed, guild, gid, blue_team, red_team, blue_avg, red_avg, team_gap_text, title_overrides=None):
    blue_value, red_value, lane_gap_value = build_classic_vertical_lineup_sections(guild, gid, blue_team, red_team, title_overrides)
    embed.description = "⚔️ **라인별 매치업**"
    embed.add_field(name="🔵 BLUE TEAM", value=blue_value or "기록 없음", inline=False)
    embed.add_field(name="🔴 RED TEAM", value=red_value or "기록 없음", inline=False)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(
        name="📊 라인별 우세",
        value=lane_gap_value or "기록 없음",
        inline=False,
    )
    return embed

def build_lineup_test_teams_from_user_data(guild, gid, queue_key):
    """서버에서 랜덤 10명을 딱 한 번 뽑고, 그 10명 안에서만 실제 안전성 규칙을 통과하는 팀을 찾는다."""
    guild_data = bot.user_data.get(gid, {})
    candidates = []
    for uid, data in iter_user_records(guild_data):
        user_info = ensure_user_format(data)
        if queue_key == NOBAN_QUEUE_NUM:
            roles = get_noban_effective_roles(user_info)
            role_scores = {role: get_noban_queue_score(user_info, role) for role in roles}
        elif queue_key == LOW_TIER_QUEUE_KEY:
            roles = get_low_tier_roles(user_info)
            role_scores = {role: int(user_info['mmr'].get(role, 0) or 0) for role in roles}
        else:
            roles = get_playable_roles(user_info)
            role_scores = {role: int(user_info['mmr'].get(role, 0) or 0) for role in roles}

        role_scores = {role: int(score) for role, score in role_scores.items() if int(score or 0) > 0}
        if not role_scores:
            continue

        representative = round(sum(role_scores.values()) / len(role_scores))
        candidates.append({
            "uid": str(uid),
            "scores": role_scores,
            "representative": representative,
        })

    if len(candidates) < 10:
        return None, None, "실제 유저 데이터가 10명 미만입니다."

    # 핵심: 테스트 1회마다 딱 10명만 랜덤 선정하고, 이후에는 절대 교체하지 않는다.
    sample = random.sample(candidates, 10)
    queue_scores = [item["representative"] for item in sample]
    queue_avg_mmr = round(sum(queue_scores) / len(queue_scores)) if queue_scores else 0
    by_uid = {item["uid"]: item for item in sample}
    uids = list(by_uid)

    def eff(uid, role):
        raw = int(by_uid[uid]["scores"].get(role, 0) or 0)
        if raw <= 0:
            return 0
        if queue_key == NOBAN_QUEUE_NUM:
            return raw
        return raw + get_additive_role_adjustment(
            raw,
            role,
            queue_avg_mmr=queue_avg_mmr,
            queue_scores=queue_scores,
            low_queue=(queue_key == LOW_TIER_QUEUE_KEY),
        )

    best = None
    best_fitness = float("-inf")
    deadline = time.monotonic() + 3.0

    # 고정된 10명 안에서 라인/팀 조합만 탐색한다.
    # 라인 점수차가 작은 페어를 일부러 우선 선택하지 않는다.
    for _attempt in range(1800):
        if time.monotonic() > deadline:
            break

        shuffled = uids[:]
        random.shuffle(shuffled)
        used = set()
        blue_assignment = []
        red_assignment = []
        failed = False

        for role in ROLES:
            options = [
                uid for uid in shuffled
                if uid not in used and int(by_uid[uid]["scores"].get(role, 0) or 0) > 0
            ]
            if len(options) < 2:
                failed = True
                break

            # 가능한 두 명을 무작위로 선택한다.
            # "라인차가 작은 조합 우선" 편향은 두지 않는다.
            first, second = random.sample(options, 2)
            if random.random() < 0.5:
                blue_uid, red_uid = first, second
            else:
                blue_uid, red_uid = second, first

            used.add(blue_uid)
            used.add(red_uid)
            blue_assignment.append(blue_uid)
            red_assignment.append(red_uid)

        if failed or len(blue_assignment) != 5 or len(red_assignment) != 5:
            continue

        blue_raws = [by_uid[blue_assignment[i]]["scores"][ROLES[i]] for i in range(5)]
        red_raws = [by_uid[red_assignment[i]]["scores"][ROLES[i]] for i in range(5)]
        blue_effs = [eff(blue_assignment[i], ROLES[i]) for i in range(5)]
        red_effs = [eff(red_assignment[i], ROLES[i]) for i in range(5)]

        # 너무 심한 라인차 / 팀 안전성 위반만 hard reject.
        # 정상 범위 안의 라인차는 억지로 최소화하지 않는다.
        if not validate_team_safety(blue_raws, red_raws, gid):
            continue
        if not validate_team_safety(blue_effs, red_effs, gid):
            continue

        b_bot = blue_effs[3] + blue_effs[4]
        r_bot = red_effs[3] + red_effs[4]
        if not validate_team(blue_effs, red_effs, b_bot, r_bot, gid=gid):
            continue

        raw_total_gap = abs(sum(blue_raws) - sum(red_raws))
        eff_total_gap = abs(sum(blue_effs) - sum(red_effs))

        # 고티어/캐리 전력이 한쪽에 몰리는 것을 막기 위해
        # 각 팀의 상위 2명 effective MMR 합 차이도 본다.
        blue_top2 = sum(sorted(blue_effs, reverse=True)[:2])
        red_top2 = sum(sorted(red_effs, reverse=True)[:2])
        carry_gap = abs(blue_top2 - red_top2)

        # 핵심 최적화는 팀 총 전력 + 캐리 전력 분배.
        # 라인별 점수차 자체는 fitness에서 제거했다.
        fitness = -(eff_total_gap * 2.0 + raw_total_gap * 0.7 + carry_gap * 1.2)

        if fitness > best_fitness:
            best_fitness = fitness
            blue_team = [
                (blue_assignment[i], ROLES[i], blue_effs[i], blue_raws[i])
                for i in range(5)
            ]
            red_team = [
                (red_assignment[i], ROLES[i], red_effs[i], red_raws[i])
                for i in range(5)
            ]
            best = (blue_team, red_team)

    if best is None:
        sampled_text = ", ".join(str(item["representative"]) for item in sorted(sample, key=lambda x: x["representative"], reverse=True))
        return (
            None,
            None,
            "이번에 랜덤으로 뽑힌 10명 안에서는 실제 라인 격차/팀 안전성 조건을 통과하는 라인업을 찾지 못했습니다. "
            f"선정된 10명 대표 MMR: {sampled_text}",
        )

    return best[0], best[1], None

def build_dummy_lineup_test_teams():
    blue_team = []
    red_team = []
    for idx, role in enumerate(ROLES, 1):
        blue_no = idx
        red_no = idx + len(ROLES)
        blue_score = random.randint(800, 3200)
        red_score = random.randint(800, 3200)
        blue_team.append((LeagueSimulationUser(990000000000000000 + blue_no, f"소환사 {blue_no}"), role, blue_score, blue_score))
        red_team.append((LeagueSimulationUser(990000000000000000 + red_no, f"소환사 {red_no}"), role, red_score, red_score))
    return blue_team, red_team

def build_arena_test_players_from_user_data(guild, gid):
    guild_data = bot.user_data.get(gid, {})
    candidates = []
    for uid, data in iter_user_records(guild_data):
        user_info = ensure_user_format(data)
        peak_mmr = get_peak_mmr(user_info.get('mmr', {}))
        if peak_mmr <= 0:
            continue
        member = guild.get_member(int(uid)) if guild else None
        user = member or LeagueSimulationUser(uid, user_info.get('lol_name') or f"소환사 {uid}")
        tier_name = get_tier_name(peak_mmr)
        candidates.append({
            "user": user,
            "uid": str(uid),
            "name": user_info.get('lol_name', getattr(user, "display_name", str(uid))),
            "score": peak_mmr,
            "tier": tier_name,
        })

    if len(candidates) < ARENA_PLAYER_COUNT:
        return None
    return random.sample(candidates, ARENA_PLAYER_COUNT)

def build_dummy_arena_test_players():
    players = []
    uid_base = 992000000000000000
    for idx in range(1, ARENA_PLAYER_COUNT + 1):
        uid = uid_base + idx
        score = random.randint(800, 3200)
        tier_name = get_tier_name(score)
        players.append({
            "user": LeagueSimulationUser(uid, f"소환사 {idx}"),
            "uid": str(uid),
            "name": f"소환사 {idx}",
            "score": score,
            "tier": tier_name,
        })
    return players

def build_arena_test_teams(gid, players):
    players = sorted(players, key=lambda item: item["score"], reverse=True)
    teams = [{"players": [], "total": 0} for _ in range(ARENA_TEAM_COUNT)]

    for player in players:
        eligible_teams = [
            team for team in teams
            if len(team["players"]) < ARENA_TEAM_SIZE
            and not team_violates_separation(
                gid,
                [item["uid"] for item in team["players"]] + [player["uid"]]
            )
        ]
        if not eligible_teams:
            return None
        target = min(
            eligible_teams,
            key=lambda team: (team["total"], len(team["players"]))
        )
        target["players"].append(player)
        target["total"] += player["score"]

    return sorted(teams, key=lambda team: team["total"], reverse=True)

def build_arena_test_embed(queue_key, teams, *, force_dummy, guild=None, gid=None):
    totals = [team["total"] for team in teams]
    avg_total = round(sum(totals) / len(totals)) if totals else 0
    gap = max(totals) - min(totals) if totals else 0
    embed = discord.Embed(
        title=f"🧪 {get_queue_label(queue_key)} 라인업 포맷 테스트",
        description=(
            f"총 18명을 **3명씩 6팀**으로 배정한 아레나 미리보기입니다.\n"
            f"기준: 각 소환사의 **라인 중 최고 MMR** · 팀 평균 총점 **{avg_total}** · 최대 격차 **{gap}**"
        ),
        color=0xf39c12
    )

    for idx, team in enumerate(teams, 1):
        member_lines = [
            f"{p['user'].mention} · {get_public_mmr_rank(p['score'])} {get_tier_emoji(p.get('tier') or get_tier_name(p['score']), guild, gid)}"
            for p in sorted(team["players"], key=lambda item: item["score"], reverse=True)
        ]
        embed.add_field(
            name=f"아레나 팀 {idx} · 총점 {team['total']}",
            value="\n".join(member_lines),
            inline=False
        )

    footer_text = (
        "소환사 1~18과 랜덤 점수(800~3200점)로 만든 샘플입니다. 팀 재계산/음성 이동은 실행하지 않습니다."
        if force_dummy else
        "서버 실제 유저 데이터에서 랜덤 18명을 뽑은 포맷 시뮬레이션입니다. 팀 재계산/음성 이동은 실행하지 않습니다."
    )
    embed.set_footer(text=footer_text)
    return embed

def build_arena_reveal_embed(teams, revealed_slots=None, phase_text="아레나 팀 추첨 시작", *, simulation=False, guild=None, gid=None):
    revealed_slots = revealed_slots or set()
    title_prefix = "시뮬레이션 · " if simulation else ""
    reveal_embed = discord.Embed(
        title=f"🎲 {title_prefix}{phase_text}",
        description="아레나 1팀부터 6팀까지 한 명씩 순서대로 공개됩니다.",
        color=0xf39c12
    )
    for idx, team in enumerate(teams, 1):
        lines = []
        for slot, player in enumerate(
            sorted(team["players"], key=lambda item: item["score"], reverse=True),
            1
        ):
            if (idx, slot) in revealed_slots:
                tier_emoji = get_tier_emoji(player.get("tier") or get_tier_name(player["score"]), guild, gid)
                lines.append(f"**{slot}번** {player['user'].mention} `{get_public_mmr_rank(player['score'])}` {tier_emoji}")
            else:
                lines.append(f"**{slot}번** ???")
        reveal_embed.add_field(
            name=f"아레나 팀 {idx} · 총점 {team['total']}",
            value="\n".join(lines),
            inline=False
        )
    reveal_embed.set_footer(text=f"공개 진행도 {len(revealed_slots)}/{ARENA_PLAYER_COUNT}")
    return reveal_embed

async def send_or_edit_arena_reveal(
    interaction,
    gid,
    teams,
    final_embed,
    *,
    simulation=False,
    use_output_channel=True,
):
    if simulation:
        output_channel = await get_league_sim_output_channel(interaction.guild, gid)
    else:
        output_channel = await get_match_output_channel(interaction.guild, gid) if use_output_channel else None
    target_channel = output_channel if output_channel and output_channel.id != interaction.channel_id else None

    if target_channel:
        reveal_message = await target_channel.send(embed=build_arena_reveal_embed(teams, simulation=simulation, guild=interaction.guild, gid=gid))
        message = (
            f"✅ 시뮬레이션 출력을 {target_channel.mention} 채널에서 진행합니다."
            if simulation else
            f"✅ 아레나 팀 추첨을 {target_channel.mention} 채널에서 진행합니다."
        )
        await interaction.followup.send(message, ephemeral=True)
    else:
        reveal_message = await interaction.followup.send(
            embed=build_arena_reveal_embed(teams, simulation=simulation, guild=interaction.guild, gid=gid),
            ephemeral=False,
            wait=True
        )

    revealed_slots = set()
    await asyncio.sleep(2)

    for idx, team in enumerate(teams, 1):
        sorted_players = sorted(team["players"], key=lambda item: item["score"], reverse=True)
        for slot, player in enumerate(sorted_players, 1):
            revealed_slots.add((idx, slot))
            phase_text = f"아레나 팀 추첨 중 · {idx}팀 {slot}번 공개"
            await reveal_message.edit(
                embed=build_arena_reveal_embed(
                    teams,
                    revealed_slots,
                    phase_text,
                    simulation=simulation,
                    guild=interaction.guild,
                    gid=gid,
                )
            )
            await asyncio.sleep(2)

    await reveal_message.edit(embed=final_embed)

def build_dummy_league_queue():
    queue_entries = []
    uid_base = 991000000000000000
    role_scores = {"탑": 1600, "정글": 1800, "미드": 2000, "원딜": 2200, "서폿": 2400}
    role_pool = []
    for role in ROLES:
        role_pool.extend([role] * LEAGUE_TEAM_COUNT)
    random.shuffle(role_pool)

    for idx, primary_role in enumerate(role_pool, 1):
        uid = uid_base + idx
        user = LeagueSimulationUser(uid, f"소환사 {idx}")
        # ponytail: 시뮬레이션은 각 팀이 같은 역할 합계를 갖게 해 무작위 자체 실패를 막는다.
        scores = dict(role_scores)
        bot.user_data.setdefault("__simulation__", {})[str(uid)] = ensure_user_format({
            "lol_name": f"소환사 {idx}",
            "mmr": scores,
            "plays": {role: 1 for role in ROLES},
            "_simulation_dummy": True,
        })
        queue_entries.append((user, time.time(), None, None, None, [primary_role]))
    return "__simulation__", queue_entries

def build_league_sim_queue_progress_embed(q, data_gid="__simulation__", guild=None, gid=None):
    lines = []
    scores = []
    tier_counts = {}
    for idx, data in enumerate(q[:LEAGUE_PLAYER_COUNT], 1):
        user, _, _, _, _ = normalize_queue_entry(data)
        roles = data[5] if len(data) > 5 and isinstance(data[5], list) else []
        role_text = "/".join(get_role_display_marker(role, guild) for role in roles if role in ROLES) or "올라운더"
        user_info = ensure_user_format(bot.user_data.get(data_gid, {}).get(str(user.id), {"mmr": {}}))
        requested_scores = [int(user_info.get("mmr", {}).get(role, 0) or 0) for role in roles if role in ROLES]
        score = max(requested_scores) if requested_scores else get_peak_mmr(user_info.get("mmr", {}))
        scores.append(score)
        tier_name = get_tier_name(score)
        tier_emoji = get_tier_emoji(tier_name, guild, gid)
        tier_counts[tier_emoji] = tier_counts.get(tier_emoji, 0) + 1
        lines.append(f"`#{idx:02}` {role_text} `{get_public_mmr_rank(score)}` {tier_emoji} **{discord.utils.escape_markdown(user.display_name)}**")

    count = min(len(q), LEAGUE_PLAYER_COUNT)
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    filled_bar = "⬜" * count
    empty_bar = "▒" * max(0, LEAGUE_PLAYER_COUNT - count)
    tier_line = " ".join(f"{emoji} x{amount}" for emoji, amount in tier_counts.items()) or "기록 없음"

    embed = discord.Embed(
        title=f"🏆 {LEAGUE_MODE_NAME} 시뮬레이션 매칭 스태터스",
        color=0x9b59b6
    )
    embed.add_field(
        name=f"**Dream To Play** · {LEAGUE_MODE_NAME} 시뮬레이션",
        value=f"{filled_bar}{empty_bar} ({count}/{LEAGUE_PLAYER_COUNT}) · 평균 Rating **{avg_score}** · 🧪 준비완료",
        inline=False
    )
    embed.add_field(
        name="참가 소환사 목록",
        value="\n".join(lines) or "기록 없음",
        inline=False
    )
    embed.add_field(
        name="현재 대기열 티어 분포도",
        value=tier_line,
        inline=False
    )
    embed.add_field(
        name="리그전 구성 준비도",
        value=f"4팀 리그전 신청 **{count}/{LEAGUE_PLAYER_COUNT}명** · 필요 인원 **{max(0, LEAGUE_PLAYER_COUNT - count)}명**\n관리자가 `/내전진행 작업:팀구성 큐:{LEAGUE_SIM_LABEL}` 입력 시 4팀과 대진표를 생성합니다.",
        inline=False
    )
    embed.set_footer(
        text="시뮬레이션 화면입니다. 실제 대기열, 전적, MMR, 음성 채널에는 반영되지 않습니다."
    )
    return embed

def build_league_sim_lineup_embed(q, data_gid="__simulation__", guild=None, gid=None):
    lines = []
    role_counts = {role: 0 for role in ROLES}
    scores = []
    for idx, data in enumerate(q[:LEAGUE_PLAYER_COUNT], 1):
        user, _, pref1, pref2, pref3 = normalize_queue_entry(data)
        uid = str(user.id)
        user_info = ensure_user_format(bot.user_data.get(data_gid, {}).get(uid, {"lol_name": user.display_name}))
        roles = data[5] if len(data) > 5 and isinstance(data[5], list) else get_requested_roles(pref1, pref2, pref3)
        roles = [role for role in roles if role in ROLES] or get_playable_roles(user_info)
        main_role = roles[0] if roles else "미정"
        if main_role in role_counts:
            role_counts[main_role] += 1
        score = int(user_info.get("mmr", {}).get(main_role, 0) or get_avg_mmr(user_info.get("mmr", {})) or 0)
        if score > 0:
            scores.append(score)
        name = discord.utils.escape_markdown(user_info.get("lol_name") or user.display_name)
        role_text = "/".join(get_role_display_marker(role, guild) for role in roles) if roles else "라인 미정"
        tier_text = f" {get_tier_emoji(get_tier_name(score), guild, gid)}" if score else ""
        score_text = f" `{get_public_mmr_rank(score)}`" if score else ""
        if len(roles) == 1 and score:
            score_display = format_match_role_score(roles[0], score, guild, gid)
            lines.append(f"`#{idx:02}` {score_display} · {name}")
        else:
            lines.append(f"`#{idx:02}` {role_text}{score_text}{tier_text} · {name}")

    count = min(len(q), LEAGUE_PLAYER_COUNT)
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    role_summary = " · ".join(f"{get_role_display_marker(role, guild)} {role_counts[role]}명" for role in ROLES)
    embed = discord.Embed(
        title=f"🏆 {LEAGUE_MODE_NAME} 시뮬레이션 라인업",
        description="\n".join(lines) if lines else "표시할 시뮬레이션 라인업이 없습니다.",
        color=0x9b59b6
    )
    embed.add_field(
        name="라인업 요약",
        value=f"신청 인원 **{count}/{LEAGUE_PLAYER_COUNT}명** · 평균 Rating **{avg_score}**\n{role_summary}",
        inline=False
    )
    embed.set_footer(text=f"/내전진행 작업:팀구성 큐:{LEAGUE_SIM_LABEL} 입력 시 이 20명 풀로 팀과 대진표를 생성합니다.")
    return embed

def build_lineup_test_title_overrides(blue_team, red_team):
    sample_titles = [
        "⚔️ 첫 번째 선봉장",
        "🌟 중앙의 선구자",
        "🎯 승부의 결정자",
        "🛡️ 패배로 가리지 못한",
        "👑 모두가 기억하는",
    ]
    title_overrides = {}
    title_index = 0
    for i in range(min(len(blue_team), len(red_team))):
        titled_team = blue_team if i % 2 == 0 else red_team
        untitled_team = red_team if i % 2 == 0 else blue_team

        titled_uid = get_lineup_user_id(titled_team[i][0])
        untitled_uid = get_lineup_user_id(untitled_team[i][0])
        title_overrides[titled_uid] = sample_titles[title_index % len(sample_titles)]
        title_overrides[untitled_uid] = ""
        title_index += 1

    return title_overrides


compact_riot_name = rules.compact_riot_name

normalize_riot_id = rules.normalize_riot_id

build_riot_id_input = rules.build_riot_id_input
















# 복수 챔피언 조건형 최초칭호. 표시 시 두 챔피언 이모지를 모두 붙일 수 있다.


































































def normalize_queue_selector(value):
    raw = str(getattr(value, "value", value) or "").strip()
    compact = re.sub(r"\s+", "", raw).lower()
    aliases = {
        "노밴모드": NOBAN_QUEUE_NUM,
        "노밴": NOBAN_QUEUE_NUM,
        "저티어큐": LOW_TIER_QUEUE_KEY,
        "저티어": LOW_TIER_QUEUE_KEY,
        "아레나(3x6)": ARENA_QUEUE_NUM,
        "아레나3x6": ARENA_QUEUE_NUM,
        "아레나": ARENA_QUEUE_NUM,
        "칼바람나락": ARAM_QUEUE_KEY,
        "칼바람/무작위총력전": ARAM_QUEUE_KEY,
        "칼바람/총력전": ARAM_QUEUE_KEY,
        "무작위총력전": ARAM_QUEUE_KEY,
        "총력전": ARAM_QUEUE_KEY,
        "협곡리그전": LEAGUE_SERIES_QUEUE_KEY,
        "토너먼트리그전": LEAGUE_SERIES_QUEUE_KEY,
        "단판토너먼트": LEAGUE_SERIES_QUEUE_KEY,  # 구형 선택값도 새 협곡 리그전으로 통합
        "칼바람리그전": ARAM_LEAGUE_QUEUE_KEY,
        "aramleague": ARAM_LEAGUE_QUEUE_KEY,
    }
    if compact in aliases:
        return aliases[compact]
    return rules.normalize_queue_selector(
        value,
        noban=NOBAN_QUEUE_NUM,
        arena=ARENA_QUEUE_NUM,
        league=LEAGUE_SERIES_QUEUE_KEY,
        league_sim=LEAGUE_SERIES_SIM_QUEUE_KEY,
        league_series=LEAGUE_SERIES_QUEUE_KEY,
        league_series_sim=LEAGUE_SERIES_SIM_QUEUE_KEY,
        aram=ARAM_QUEUE_KEY,
        low_tier=LOW_TIER_QUEUE_KEY,
    )

def get_queue_label(queue_key):
    if queue_key == "retro":
        return "ROFL 소급"
    if queue_key == NOBAN_QUEUE_NUM:
        return "노밴 모드"
    if queue_key == ARENA_QUEUE_NUM:
        return "아레나(3x6)"
    if queue_key == LEAGUE_QUEUE_KEY:
        return LEAGUE_SERIES_MODE_NAME
    if queue_key == LEAGUE_SERIES_QUEUE_KEY:
        return LEAGUE_SERIES_MODE_NAME
    if queue_key == ARAM_LEAGUE_QUEUE_KEY:
        return ARAM_LEAGUE_MODE_NAME
    if queue_key == LEAGUE_SERIES_SIM_QUEUE_KEY:
        return LEAGUE_SERIES_SIM_LABEL
    if queue_key == LEAGUE_SIM_QUEUE_KEY:
        return LEAGUE_SIM_LABEL
    if queue_key == ARAM_QUEUE_KEY:
        return "칼바람 나락"
    if queue_key == LOW_TIER_QUEUE_KEY:
        return "저티어 큐"
    return f"{queue_key}번"

def get_required_count(queue_key):
    if queue_key == ARENA_QUEUE_NUM:
        return ARENA_PLAYER_COUNT
    if queue_key == LEAGUE_QUEUE_KEY:
        return LEAGUE_PLAYER_COUNT
    if queue_key == LEAGUE_SERIES_QUEUE_KEY:
        return LEAGUE_SERIES_MAX_PLAYER_COUNT
    if queue_key == LEAGUE_SERIES_SIM_QUEUE_KEY:
        return LEAGUE_SERIES_MAX_PLAYER_COUNT
    if queue_key == ARAM_LEAGUE_QUEUE_KEY:
        return ARAM_LEAGUE_MAX_PLAYER_COUNT
    if queue_key == ARAM_QUEUE_KEY:
        return ARAM_PLAYER_COUNT
    return 10

def get_queue_exclusivity_group(queue_key):
    normalized = normalize_queue_selector(queue_key)
    queue_key = normalized if normalized is not None else queue_key
    if isinstance(queue_key, int) and 1 <= queue_key <= 5:
        return "normal"
    if queue_key == NOBAN_QUEUE_NUM:
        return "noban"
    if queue_key == LOW_TIER_QUEUE_KEY:
        return "low_tier"
    if queue_key == ARENA_QUEUE_NUM:
        return "arena"
    if queue_key == ARAM_QUEUE_KEY:
        return "aram"
    if queue_key == LEAGUE_QUEUE_KEY:
        return "league"
    if queue_key == LEAGUE_SERIES_QUEUE_KEY:
        return "league_series"
    if queue_key == ARAM_LEAGUE_QUEUE_KEY:
        return "aram_league"
    return str(queue_key)

def ensure_guild_queues(gid):
    queues = bot.queues.setdefault(gid, {i: [] for i in range(1, 7)})
    for i in range(1, 7):
        queues.setdefault(i, [])
    queues.setdefault(ARENA_QUEUE_NUM, [])
    queues.setdefault(LEAGUE_QUEUE_KEY, [])
    queues.setdefault(LEAGUE_SIM_QUEUE_KEY, [])
    queues.setdefault(LEAGUE_SERIES_QUEUE_KEY, [])
    queues.setdefault(LEAGUE_SERIES_SIM_QUEUE_KEY, [])
    queues.setdefault(ARAM_LEAGUE_QUEUE_KEY, [])
    # 구형 20명 단판 토너먼트 대기열은 새 협곡 리그전 대기열로 자동 통합한다.
    legacy_league_q = queues.get(LEAGUE_QUEUE_KEY, [])
    if legacy_league_q:
        existing_ids = {str(normalize_queue_entry(entry)[0].id) for entry in queues[LEAGUE_SERIES_QUEUE_KEY]}
        for entry in legacy_league_q:
            user = normalize_queue_entry(entry)[0]
            if str(user.id) not in existing_ids:
                queues[LEAGUE_SERIES_QUEUE_KEY].append(entry)
                existing_ids.add(str(user.id))
        queues[LEAGUE_QUEUE_KEY] = []
    queues.setdefault(ARAM_QUEUE_KEY, [])
    queues.setdefault(LOW_TIER_QUEUE_KEY, [])
    return queues

def touch_queue(gid, queue_key):
    gid = str(gid)
    bot.queue_updated_at.setdefault(gid, {})[queue_key] = time.time()
    controller = getattr(bot, "queue_controller", None)
    if controller is not None:
        controller.mark_dirty(gid, queue_key)
    scheduler = globals().get("schedule_participation_panel_refresh")
    if scheduler:
        scheduler(gid)
    admin_scheduler = globals().get("schedule_party_admin_panel_refresh")
    if admin_scheduler:
        admin_scheduler(gid)

def get_queue_last_changed_at(gid, queue_key, entries):
    touched = bot.queue_updated_at.setdefault(str(gid), {}).get(queue_key)
    if touched:
        return touched
    entry_times = []
    for entry in entries or []:
        try:
            entry_times.append(float(entry[1]))
        except (IndexError, TypeError, ValueError):
            continue
    return max(entry_times) if entry_times else time.time()

def get_queue_entry_joined_at(entry):
    try:
        return float(entry[1])
    except (IndexError, TypeError, ValueError):
        return time.time()

async def get_queue_notice_channel(guild, gid, queue_key=None):
    if queue_key in (LEAGUE_QUEUE_KEY, LEAGUE_SIM_QUEUE_KEY, LEAGUE_SERIES_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY):
        channel = await get_league_output_channel(guild, gid)
        if channel:
            return channel
    channel = await get_match_output_channel(guild, gid)
    if channel:
        return channel
    if guild and guild.system_channel:
        return guild.system_channel
    if guild:
        for channel in guild.text_channels:
            permissions = channel.permissions_for(guild.me)
            if permissions.send_messages:
                return channel
    return None


def claim_coach_discord_notification():
    """Claim one queued web reservation notification without holding the event loop."""
    if not bot.db_enabled:
        return None
    try:
        with bot.get_db_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE coach_discord_notification_queue
                        SET status = 'pending', updated_at = NOW()
                        WHERE status = 'sending' AND updated_at < NOW() - INTERVAL '10 minutes'
                        """
                    )
                    cur.execute(
                        """
                        WITH candidate AS (
                            SELECT id
                            FROM coach_discord_notification_queue
                            WHERE status = 'pending' AND available_at <= NOW()
                            ORDER BY created_at ASC
                            FOR UPDATE SKIP LOCKED
                            LIMIT 1
                        )
                        UPDATE coach_discord_notification_queue q
                        SET status = 'sending', attempts = q.attempts + 1, updated_at = NOW()
                        FROM candidate
                        WHERE q.id = candidate.id
                        RETURNING q.id, q.discord_subject, q.event, q.payload, q.attempts
                        """
                    )
                    return cur.fetchone()
    except Exception as exc:
        logger.warning("코치 Discord 알림 큐 조회 실패: %s", type(exc).__name__)
        return None


def finish_coach_discord_notification(notification_id, *, sent=False, error=""):
    if not bot.db_enabled or not notification_id:
        return
    try:
        with bot.get_db_connection() as conn:
            with conn.cursor() as cur:
                if sent:
                    cur.execute(
                        """
                        UPDATE coach_discord_notification_queue
                        SET status = 'sent', sent_at = NOW(), updated_at = NOW(), last_error = ''
                        WHERE id = %s
                        """,
                        (notification_id,),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE coach_discord_notification_queue
                        SET status = CASE WHEN attempts >= 3 THEN 'failed' ELSE 'pending' END,
                            available_at = NOW() + INTERVAL '1 minute',
                            last_error = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (str(error or "")[:160], notification_id),
                    )
    except Exception as exc:
        logger.warning("코치 Discord 알림 상태 저장 실패: %s", type(exc).__name__)


@tasks.loop(seconds=30)
async def coach_discord_notification_loop():
    for _ in range(10):
        row = await asyncio.to_thread(claim_coach_discord_notification)
        if not row:
            return
        notification_id, subject, event, payload, attempts = row
        try:
            subject = str(subject or "")
            if not subject.isascii() or not subject.isdigit() or len(subject) > 20:
                raise ValueError("invalid_discord_subject")
            target = await bot.fetch_user(int(subject))
            data = payload if isinstance(payload, dict) else {}
            embed = discord.Embed(
                title="새 코칭 예약",
                description="코치님에게 새 예약이 접수되었습니다.",
                color=0x5865F2,
            )
            if data.get("coachName"):
                embed.add_field(name="강의", value=str(data.get("coachName") or "")[:120], inline=False)
            if data.get("preferredTime"):
                embed.add_field(name="희망 시간", value=str(data.get("preferredTime") or "")[:160], inline=False)
            embed.set_footer(text="상세 수강생 정보는 코치 관리 화면에서 확인하세요.")
            await target.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            await asyncio.to_thread(finish_coach_discord_notification, notification_id, sent=True)
        except Exception as exc:
            await asyncio.to_thread(
                finish_coach_discord_notification,
                notification_id,
                sent=False,
                error=type(exc).__name__,
            )

@tasks.loop(minutes=5)
async def stale_queue_cleanup_loop():
    now_ts = time.time()
    changed_guilds = set()
    for guild in bot.guilds:
        gid = str(guild.id)
        await finalize_expired_league_champion_name(guild, gid)
        queues = ensure_guild_queues(gid)
        for queue_key, entries in list(queues.items()):
            if not entries:
                continue
            if queue_has_active_recruitment(gid, queue_key):
                continue
            if bot.active_games.get(gid, {}).get(queue_key):
                continue
            if (gid, queue_key) in bot.processing_lineups:
                continue
            expired_indexes = {
                index for index, entry in enumerate(entries)
                if now_ts - get_queue_entry_joined_at(entry) >= QUEUE_ENTRY_TIMEOUT_SECONDS
            }
            if not expired_indexes:
                continue

            removed_mentions = []
            for index in sorted(expired_indexes):
                entry = entries[index]
                user = entry[0] if entry else None
                removed_mentions.append(user.mention if user else "알 수 없음")
            queues[queue_key] = [
                entry for index, entry in enumerate(entries)
                if index not in expired_indexes
            ]
            # Keep the participation panel in sync with automatic queue removals.
            touch_queue(gid, queue_key)
            if not queues[queue_key]:
                bot.queue_updated_at.setdefault(gid, {}).pop(queue_key, None)
            changed_guilds.add(gid)

            channel = await get_queue_notice_channel(guild, gid, queue_key)
            if channel:
                required_count = get_required_count(queue_key)
                embed = discord.Embed(
                    title="⏰ 대기열 자동 취소",
                    description=(
                        f"**{get_queue_label(queue_key)}** 대기열 신청 후 90분이 지나 자동 취소되었습니다.\n"
                        f"취소 인원: **{len(removed_mentions)}명** / 현재 인원 **{len(queues[queue_key])}/{required_count}명**"
                    ),
                    color=0xe67e22,
                )
                embed.add_field(name="취소된 신청자", value="\n".join(removed_mentions[:20]), inline=False)
                embed.set_footer(text="다시 진행하려면 /참가 로 새로 신청해주세요.")
                try:
                    await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    pass

    for gid in changed_guilds:
        bot.save_lucid_data(gid)
        schedule_participation_panel_refresh(gid, delay=0.8)


def get_title_thresholds(gid):
    key = get_match_frequency_key(gid)
    return TITLE_THRESHOLD_PRESETS.get(key, TITLE_THRESHOLD_PRESETS[DEFAULT_MATCH_FREQUENCY])

def get_queue_sort_score(gid, data, queue_key):
    user, _, pref1, pref2, pref3 = normalize_queue_entry(data)
    user_data_map = bot.user_data.get(gid, {}).get(str(user.id), {'mmr': 0})
    user_info = ensure_user_format(user_data_map)
    if queue_key in (ARENA_QUEUE_NUM, ARAM_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY):
        return get_peak_mmr(user_info.get('mmr', 0))
    if queue_key == NOBAN_QUEUE_NUM:
        return get_noban_queue_display_mmr(user_info, pref1, pref2, pref3)
    if queue_key == LOW_TIER_QUEUE_KEY:
        if is_low_tier_force_entry(data):
            return get_queue_display_mmr(user_info, pref1, pref2, pref3)
        return get_low_tier_queue_display_mmr(user_info, pref1, pref2, pref3)
    return get_queue_display_mmr(user_info, pref1, pref2, pref3)

def get_league_round(gid):
    guild_data = bot.user_data.setdefault(gid, {})
    return int(guild_data.get(LEAGUE_ROUND_KEY, 0))

def get_next_league_round(gid):
    return get_league_round(gid) + 1

def set_league_round(gid, round_no):
    bot.user_data.setdefault(gid, {})[LEAGUE_ROUND_KEY] = int(round_no)

def get_league_series_round(gid):
    guild_data = bot.user_data.setdefault(gid, {})
    return int(guild_data.get(LEAGUE_SERIES_ROUND_KEY, 0))

def get_next_league_series_round(gid):
    return get_league_series_round(gid) + 1

def set_league_series_round(gid, round_no):
    bot.user_data.setdefault(gid, {})[LEAGUE_SERIES_ROUND_KEY] = int(round_no)

def get_aram_league_round(gid):
    return safe_detail_int(bot.user_data.setdefault(str(gid), {}).get(ARAM_LEAGUE_ROUND_KEY, 0))

def get_next_aram_league_round(gid):
    return get_aram_league_round(gid) + 1

def set_aram_league_round(gid, round_no):
    bot.user_data.setdefault(str(gid), {})[ARAM_LEAGUE_ROUND_KEY] = max(0, int(round_no or 0))


def get_league_champions(gid):
    return bot.user_data.setdefault(gid, {}).setdefault(LEAGUE_CHAMPIONS_KEY, [])

def get_team_display_names(guild, gid, team):
    return [
        get_member_display_name(guild, gid, uid)
        for uid in team.get("players", [])
    ]

def get_user_peak_tier_emoji(gid, uid, guild=None):
    data = bot.user_data.get(gid, {}).get(str(uid), {})
    if not isinstance(data, dict):
        return "❔"
    user_info = ensure_user_format(data)
    tier_name = get_tier_name(get_peak_mmr(user_info.get("mmr", 0)))
    return get_tier_emoji(tier_name, guild, gid)

def format_league_player_name(guild, gid, uid):
    return f"{get_user_peak_tier_emoji(gid, uid, guild)} {get_member_display_name(guild, gid, uid)}"

def format_league_player_name_from_team(guild, gid, team, uid):
    player_names = team.get("player_names", {}) or {}
    player_scores = team.get("player_scores", {}) or {}
    uid_key = str(uid)
    if uid_key in player_names:
        score = int(player_scores.get(uid_key, 0) or 0)
        tier_name = get_tier_name(score) if score > 0 else None
        emoji = get_tier_emoji(tier_name, guild, gid) if tier_name else "❔"
        return f"{emoji} {player_names[uid_key]}"
    return format_league_player_name(guild, gid, uid)

def format_league_team_name(team):
    team_name = str(team.get("name") or "").strip()
    team_no = team.get("team_no")
    generated_names = {
        f"{LEAGUE_MODE_NAME} {team_no}팀",
        f"토너먼트 {team_no}팀",
        f"{LEAGUE_SERIES_MODE_NAME} {team_no}팀",
        f"토너먼트(4강) {team_no}팀",
    }
    generated_pattern = rf"^(?:{re.escape(LEAGUE_MODE_NAME)}|토너먼트|{re.escape(LEAGUE_SERIES_MODE_NAME)}|토너먼트\(4강\))\s*{re.escape(str(team_no))}팀$"
    if team_no and (not team_name or team_name in generated_names or re.fullmatch(generated_pattern, team_name)):
        return f"{team_no}팀"
    return team_name or f"{LEAGUE_TITLE_NAME} 팀"

def format_league_result_team_label(team):
    team_name = str(team.get("name") or "").strip()
    if re.fullmatch(r"\d+회차\s*(우승팀|준우승팀)", team_name):
        team = {**team, "name": ""}
    return format_league_team_name(team)

def format_league_result_field_name(icon, label, team):
    return f"{icon} {label} · {format_league_result_team_label(team)}"

def format_league_medal_line(gold=0, silver=0, bronze=0):
    parts = []
    gold = max(0, int(gold or 0))
    silver = max(0, int(silver or 0))
    bronze = max(0, int(bronze or 0))
    if gold:
        parts.append(f"🥇 금 {gold}회")
    if silver:
        parts.append(f"🥈 은 {silver}회")
    if bronze:
        parts.append(f"🥉 동 {bronze}회")
    return " · ".join(parts)

def format_league_match_summary(stats):
    match_wins = int(stats.get("match_win", 0) or 0)
    match_losses = int(stats.get("match_loss", 0) or 0)
    match_total = match_wins + match_losses
    participations = int(stats.get("participations", 0) or 0)
    record_text = f"매치 **{match_total}전 {match_wins}승**"
    if match_losses:
        record_text += f" {match_losses}패"
    return f"{record_text}  ( {participations}회 참가 )"

def format_league_team_summary(guild, gid, team):
    names = ", ".join(
        format_league_player_name_from_team(guild, gid, team, uid)
        for uid in team.get("players", [])
    )
    return f"{format_league_team_name(team)}({names})"

def format_league_role_lines(guild, gid, team):
    if team.get("roles"):
        return format_league_series_role_lines(guild, gid, team)
    roles_map = team.get("roles", {})
    lines = []
    for role in ROLES:
        uid = roles_map.get(role)
        if uid:
            lines.append(f"{role}) {format_league_player_name_from_team(guild, gid, team, uid)}")
        else:
            lines.append(f"{role}) 기록 없음")
    return "\n".join(lines)

def format_inline_code_text(value, max_len=28):
    text = str(value or "-").replace("`", "'").strip()
    if len(text) > max_len:
        text = text[:max_len - 1] + "…"
    return text

def format_league_series_role_lines(guild, gid, team):
    roles_map = team.get("roles", {}) or {}
    player_names = team.get("player_names", {}) or {}
    player_scores = team.get("player_scores", {}) or {}
    lines = []
    if not roles_map:
        for uid in team.get("players", []) or []:
            uid_key = str(uid)
            name = player_names.get(uid_key) or get_member_display_name(guild, gid, uid_key)
            score = int(player_scores.get(uid_key, 0) or 0)
            tier = get_tier_name(score) if score > 0 else "미배치"
            tier_emoji = get_tier_emoji(tier, guild, gid) if score > 0 else "❔"
            lines.append(f"{tier_emoji} **{get_public_mmr_rank(score)}** `{format_inline_code_text(name)}`")
        return "\n".join(lines) or "기록 없음"
    for role in ROLES:
        uid = roles_map.get(role)
        role_marker = get_role_display_marker(role, guild)
        if not uid:
            lines.append(f"{role_marker} ❔ `기록 없음`")
            continue
        uid_key = str(uid)
        name = player_names.get(uid_key) or get_member_display_name(guild, gid, uid_key)
        score = int(player_scores.get(uid_key, 0) or 0)
        score_display = format_match_role_score(role, score, guild, gid) if score > 0 else f"{role_marker} 기록 없음 ❔"
        lines.append(f"{score_display} `{format_inline_code_text(name)}`")
    return "\n".join(lines)

def build_league_match_detail_embed(guild, gid, match_no, blue_team, red_team, *, footer_text=None):
    blue_total = int(blue_team.get("total", blue_team.get("display_total", 0)) or 0)
    red_total = int(red_team.get("total", red_team.get("display_total", 0)) or 0)
    gap = blue_total - red_total
    if gap == 0:
        gap_text = "전력차 **0** · 균형"
    else:
        favored_no = blue_team["team_no"] if gap > 0 else red_team["team_no"]
        gap_text = f"전력차 **{abs(gap)}** · {favored_no}팀 우세"

    round_label = "결승" if int(match_no) == 3 else "4강"
    embed = discord.Embed(
        title=f"⚔️ {LEAGUE_MODE_NAME} [{round_label}] 매치 {match_no}",
        description=(
            f"🔵 **{format_league_team_name(blue_team)}** `{blue_total}` vs `{red_total}` "
            f"**{format_league_team_name(red_team)}** 🔴\n{gap_text}"
        ),
        color=0x3498db if int(match_no) != 3 else 0xf1c40f,
    )
    embed.add_field(
        name=f"BLUE · {format_league_team_name(blue_team)}",
        value=format_league_series_role_lines(guild, gid, blue_team),
        inline=False,
    )
    embed.add_field(
        name=f"RED · {format_league_team_name(red_team)}",
        value=format_league_series_role_lines(guild, gid, red_team),
        inline=False,
    )
    if footer_text:
        embed.set_footer(text=footer_text)
    return embed













RIVAL_MIN_GAMES = 7
RIVAL_MIN_WINRATE = 35.0
RIVAL_MAX_WINRATE = 65.0
RIVAL_FATE_MATCH_GAMES = 8
RIVAL_NAMED_WIN_WINS = 6
RIVAL_TITLE_MATCHES = 12


































guides.configure(
    bot=bot,
    logger=logger,
    is_feature_enabled=is_feature_enabled,
    LEAGUE_MODE_NAME=LEAGUE_MODE_NAME,
    LOW_TIER_MMR_LIMIT=LOW_TIER_MMR_LIMIT,
    HELP_GUIDE_EDIT_DELAY_SECONDS=HELP_GUIDE_EDIT_DELAY_SECONDS,
    HELP_GUIDE_FORUM_LAYOUT_VERSION=HELP_GUIDE_FORUM_LAYOUT_VERSION,
    HELP_GUIDE_FORUM_THREADS_KEY=HELP_GUIDE_FORUM_THREADS_KEY,
    HELP_GUIDE_KEY=HELP_GUIDE_KEY,
    ADMIN_HELP_GUIDE_KEY=ADMIN_HELP_GUIDE_KEY,
    STREAMING_HELP_GUIDE_KEY=STREAMING_HELP_GUIDE_KEY,
)

ansi = guides.ansi
should_hide_help_line_for_features = guides.should_hide_help_line_for_features
filter_help_sections_for_features = guides.filter_help_sections_for_features
build_help_guide_messages = guides.build_help_guide_messages
get_help_forum_description = guides.get_help_forum_description
extract_help_forum_title = guides.extract_help_forum_title
fetch_forum_thread_and_message = guides.fetch_forum_thread_and_message
iter_forum_threads_for_cleanup = guides.iter_forum_threads_for_cleanup
is_lucid_help_content = guides.is_lucid_help_content
is_lucid_help_thread = guides.is_lucid_help_thread
get_help_title_variants = guides.get_help_title_variants
fetch_thread_starter_message = guides.fetch_thread_starter_message
split_help_forum_content = guides.split_help_forum_content
is_lucid_help_detail_content = guides.is_lucid_help_detail_content
fetch_thread_detail_message = guides.fetch_thread_detail_message
update_help_forum = guides.update_help_forum
collect_existing_help_channel_messages = guides.collect_existing_help_channel_messages
help_content_title_variants = guides.help_content_title_variants
update_help_channel_messages = guides.update_help_channel_messages
build_admin_help_guide_messages = guides.build_admin_help_guide_messages
build_streaming_help_guide_messages = guides.build_streaming_help_guide_messages
run_help_guide_coverage_check = guides.run_help_guide_coverage_check
update_help_guide = guides.update_help_guide
update_admin_help_guide = guides.update_admin_help_guide
refresh_all_help_guides_in_place = guides.refresh_all_help_guides_in_place
update_streaming_help_guide = guides.update_streaming_help_guide




async def get_match_output_channel(guild, gid):
    channel_id = bot.user_data.get(gid, {}).get(MATCH_OUTPUT_CHANNEL_KEY)
    if not channel_id:
        return None
    try:
        return guild.get_channel(int(channel_id)) if guild else None
    except (TypeError, ValueError):
        return None

async def get_league_output_channel(guild, gid):
    channel_id = bot.user_data.get(gid, {}).get(LEAGUE_OUTPUT_CHANNEL_KEY)
    if not channel_id:
        return await get_match_output_channel(guild, gid)
    try:
        return guild.get_channel(int(channel_id)) if guild else None
    except (TypeError, ValueError):
        return await get_match_output_channel(guild, gid)

async def get_league_sim_output_channel(guild, gid):
    channel_id = bot.user_data.get(gid, {}).get(LEAGUE_SIM_OUTPUT_CHANNEL_KEY)
    if not channel_id:
        return None
    try:
        return guild.get_channel(int(channel_id)) if guild else None
    except (TypeError, ValueError):
        return None

async def send_match_output(interaction, gid, **kwargs):
    notify = kwargs.pop("notify", True)
    channel = await get_match_output_channel(interaction.guild, gid)

    if channel and channel.id != interaction.channel_id:
        # This is the actual result output. If this fails, propagate the error
        # because the requested result was not delivered.
        await channel.send(**kwargs)

        # The small ephemeral "sent to channel" notice is optional UI only.
        # interaction.followup is a Webhook and the installed discord.py
        # implementation does not accept delete_after. More importantly, a
        # failure here must not make a completed match look like it failed.
        if notify:
            notice = f"✅ 결과를 {channel.mention} 채널에 전송했습니다."
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        notice,
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        notice,
                        ephemeral=True,
                    )
            except Exception as exc:
                logger.warning(
                    "경기 결과 전송 안내 메시지 실패: guild_id=%s channel_id=%s error=%s",
                    getattr(interaction, "guild_id", None),
                    getattr(channel, "id", None),
                    exc,
                )
        return

    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)

async def send_league_output(interaction, gid, **kwargs):
    notify = kwargs.pop("notify", True)
    channel = await get_league_output_channel(interaction.guild, gid)
    if channel and channel.id != interaction.channel_id:
        await channel.send(**kwargs)
        if notify:
            message = f"✅ {LEAGUE_MODE_NAME} 공지를 {channel.mention} 채널에 전송했습니다."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        return

    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)

async def send_league_sim_output(interaction, gid, **kwargs):
    notify = kwargs.pop("notify", True)
    channel = await get_league_sim_output_channel(interaction.guild, gid)
    if channel and channel.id != interaction.channel_id:
        sent_message = await channel.send(**kwargs)
        if notify:
            message = f"✅ 시뮬레이션 출력을 {channel.mention} 채널에 전송했습니다."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        return sent_message

    if interaction.response.is_done():
        return await interaction.followup.send(**kwargs, wait=True)

    await interaction.response.send_message(**kwargs)
    try:
        return await interaction.original_response()
    except discord.HTTPException:
        return None

parse_history_time = rules.parse_history_time

parse_date_option = rules.parse_date_option

now_kst = rules.now_kst

def get_valid_match_history(gid):
    records = []
    for record in get_match_history(gid):
        if record.get('cancelled'):
            continue
        if not parse_history_time(record):
            continue
        records.append(record)
    return records

def count_recent_match_history(gid, days):
    cutoff = now_kst() - timedelta(days=days)
    count = 0
    for record in get_valid_match_history(gid):
        parsed = parse_history_time(record)
        if parsed and parsed >= cutoff:
            count += 1
    return count

def resolve_detail_duration_seconds(guild_data, record, uid=None, explicit_duration=""):
    if explicit_duration:
        return match_stats.parse_duration_seconds(explicit_duration)

    match_id = str(record.get("id"))
    match_entries = match_stats.get_store(guild_data).get(match_id, {})
    if uid:
        existing = match_entries.get(str(uid), {})
        duration_seconds = int(existing.get("duration_seconds", 0) or 0)
        if duration_seconds > 0:
            return duration_seconds

    duration_candidates = [
        int(entry.get("duration_seconds", 0) or 0)
        for entry in match_entries.values()
        if int(entry.get("duration_seconds", 0) or 0) > 0
    ]
    if duration_candidates:
        return max(duration_candidates)

    return match_stats.parse_duration_seconds(record.get("duration") or "")

def format_history_duration_suffix(gid, record):
    duration_seconds = resolve_detail_duration_seconds(bot.user_data.get(gid, {}), record)
    if duration_seconds <= 0:
        return ""
    return f" ( {match_stats.format_duration(duration_seconds).replace(':', ' : ')} )"

def sync_match_duration(guild_data, record, duration_seconds):
    duration_seconds = int(duration_seconds or 0)
    if duration_seconds <= 0:
        return

    duration_text = match_stats.format_duration(duration_seconds)
    record["duration"] = duration_text
    match_entries = match_stats.get_store(guild_data).get(str(record.get("id")), {})
    duration_minutes = duration_seconds / 60

    for entry in match_entries.values():
        entry["duration_seconds"] = duration_seconds
        entry["duration"] = duration_text
        entry["csm"] = match_stats.safe_div(int(entry.get("cs", 0) or 0), duration_minutes)
        entry["gpm"] = match_stats.safe_div(int(entry.get("gold", 0) or 0), duration_minutes)
        entry["dpm"] = match_stats.safe_div(int(entry.get("damage", 0) or 0), duration_minutes)

def rebuild_role_stats_from_history(gid, uid):
    uid = str(uid)
    rebuilt = {role: {'win': 0, 'loss': 0} for role in ROLES}
    for record in get_valid_match_history(gid):
        mode = record.get("mode", "classic")
        if mode not in ("classic", LOW_TIER_MODE_KEY):
            continue
        for player in record.get("players", []):
            if str(player.get("user_id")) != uid:
                continue
            role = player.get("role")
            result = player.get("result")
            if role not in rebuilt:
                continue
            if result == "win":
                rebuilt[role]["win"] += 1
            elif result == "loss":
                rebuilt[role]["loss"] += 1
    return rebuilt

def get_display_role_stats(gid, uid, user_info):
    user_info = ensure_user_format(user_info)
    saved_stats = user_info.get("role_stats", {})
    rebuilt = rebuild_role_stats_from_history(gid, uid)
    display_stats = {}
    for role in ROLES:
        saved = saved_stats.get(role, {'win': 0, 'loss': 0})
        saved_total = saved.get("win", 0) + saved.get("loss", 0)
        rebuilt_total = rebuilt[role]["win"] + rebuilt[role]["loss"]
        played = user_info.get("plays", {}).get(role, 0)
        if rebuilt_total and (saved_total != played or rebuilt_total > saved_total):
            display_stats[role] = rebuilt[role]
        else:
            display_stats[role] = saved
    return display_stats

def restore_user_role_stats_from_history(gid, uid):
    user_info = bot.user_data.get(gid, {}).get(str(uid))
    if not isinstance(user_info, dict):
        return None
    user_info = ensure_user_format(user_info)
    rebuilt = rebuild_role_stats_from_history(gid, uid)
    restored_games = sum(rebuilt[role]["win"] + rebuilt[role]["loss"] for role in ROLES)
    if restored_games <= 0:
        return None
    for role in ROLES:
        rebuilt[role]["streak"] = int(user_info["role_stats"][role].get("streak", 0) or 0)
    user_info["role_stats"] = rebuilt
    return rebuilt

def get_role_initial_mmr(user_info, role, fallback=0):
    scores = user_info.get("eval_scores", {}).get(role, [])
    if scores:
        return int(sum(scores) / len(scores))
    return int(fallback or 0)

def estimate_role_record_by_score(gid, user_info, role, initial_mmr=None):
    user_info = ensure_user_format(user_info)
    games = int(user_info.get("plays", {}).get(role, 0) or 0)
    if games <= 0:
        return {"wins": 0, "losses": 0, "score": 0, "error": 0, "estimated_mmr": int(initial_mmr or 0)}

    current_mmr = int(user_info.get("mmr", {}).get(role, 0) or 0)
    start_mmr = int(initial_mmr if initial_mmr is not None else get_role_initial_mmr(user_info, role, current_mmr))
    target_diff = current_mmr - start_mmr
    deltas = [get_role_match_delta_config(gid, idx)[0] for idx in range(games)]
    total_delta = sum(deltas)

    sums_by_wins = {0: {0}}
    for delta in deltas:
        next_sums = {count: set(values) for count, values in sums_by_wins.items()}
        for count, values in sums_by_wins.items():
            if count + 1 > games:
                continue
            bucket = next_sums.setdefault(count + 1, set())
            for value in values:
                bucket.add(value + delta)
        sums_by_wins = next_sums

    best = None
    for wins, candidates in sums_by_wins.items():
        losses = games - wins
        for win_sum in candidates:
            net = (win_sum * 2) - total_delta
            error = abs(net - target_diff)
            candidate = {
                "wins": wins,
                "losses": losses,
                "score": net,
                "error": error,
                "estimated_mmr": start_mmr + net,
            }
            if best is None or (candidate["error"], abs(candidate["wins"] - candidate["losses"])) < (best["error"], abs(best["wins"] - best["losses"])):
                best = candidate
    return best or {"wins": 0, "losses": games, "score": -total_delta, "error": abs(-total_delta - target_diff), "estimated_mmr": start_mmr - total_delta}

def infer_role_record_with_overall(gid, user_info, target_role, initial_mmr):
    user_info = ensure_user_format(user_info)
    target_games = int(user_info.get("plays", {}).get(target_role, 0) or 0)
    overall_wins = int(user_info.get("win", 0) or 0)
    overall_losses = int(user_info.get("loss", 0) or 0)

    other_wins = 0
    other_losses = 0
    other_details = []
    for role in ROLES:
        if role == target_role:
            continue
        games = int(user_info.get("plays", {}).get(role, 0) or 0)
        if games <= 0:
            continue
        saved = user_info.get("role_stats", {}).get(role, {})
        saved_wins = int(saved.get("win", 0) or 0)
        saved_losses = int(saved.get("loss", 0) or 0)
        if saved_wins + saved_losses == games:
            wins, losses, source = saved_wins, saved_losses, "저장값"
        else:
            start = get_role_initial_mmr(user_info, role, user_info.get("mmr", {}).get(role, 0))
            estimated = estimate_role_record_by_score(gid, user_info, role, start)
            wins, losses, source = estimated["wins"], estimated["losses"], "점수추정"
        other_wins += wins
        other_losses += losses
        other_details.append((role, games, wins, losses, source))

    residual_wins = overall_wins - other_wins
    residual_losses = overall_losses - other_losses
    if residual_wins >= 0 and residual_losses >= 0 and residual_wins + residual_losses == target_games:
        return {
            "wins": residual_wins,
            "losses": residual_losses,
            "source": "전체 전적 잔여값",
            "other_details": other_details,
        }

    estimated = estimate_role_record_by_score(gid, user_info, target_role, initial_mmr)
    return {
        "wins": estimated["wins"],
        "losses": estimated["losses"],
        "source": f"점수추정(오차 {estimated['error']}점)",
        "other_details": other_details,
    }

def estimate_role_record_range(gid, games, start_mmr, end_mmr):
    games = int(games or 0)
    start_mmr = int(start_mmr or 0)
    end_mmr = int(end_mmr or 0)
    if games <= 0:
        return {"wins": 0, "losses": 0, "score": 0, "error": abs(end_mmr - start_mmr), "estimated_mmr": start_mmr}

    target_diff = end_mmr - start_mmr
    deltas = [get_role_match_delta_config(gid, idx)[0] for idx in range(games)]
    total_delta = sum(deltas)
    sums_by_wins = {0: {0}}

    for delta in deltas:
        next_sums = {count: set(values) for count, values in sums_by_wins.items()}
        for count, values in sums_by_wins.items():
            bucket = next_sums.setdefault(count + 1, set())
            for value in values:
                bucket.add(value + delta)
        sums_by_wins = next_sums

    best = None
    for wins, candidates in sums_by_wins.items():
        losses = games - wins
        for win_sum in candidates:
            net = (win_sum * 2) - total_delta
            error = abs(net - target_diff)
            candidate = {
                "wins": wins,
                "losses": losses,
                "score": net,
                "error": error,
                "estimated_mmr": start_mmr + net,
            }
            if best is None or (candidate["error"], abs(candidate["wins"] - candidate["losses"])) < (best["error"], abs(best["wins"] - best["losses"])):
                best = candidate
    return best or {"wins": 0, "losses": games, "score": -total_delta, "error": abs(-total_delta - target_diff), "estimated_mmr": start_mmr - total_delta}

def get_role_history_entries(gid, uid, role):
    uid = str(uid)
    entries = []
    for record in sorted(get_valid_match_history(gid), key=parse_history_time):
        mode = record.get("mode", "classic")
        if mode not in ("classic", LOW_TIER_MODE_KEY):
            continue
        for player in record.get("players", []):
            if str(player.get("user_id")) != uid or player.get("role") != role:
                continue
            if player.get("result") not in ("win", "loss"):
                continue
            entries.append((record, player))
    return entries

def infer_auto_role_record(gid, uid, user_info, role):
    user_info = ensure_user_format(user_info)
    total_games = int(user_info.get("plays", {}).get(role, 0) or 0)
    saved = user_info.get("role_stats", {}).get(role, {})
    saved_wins = int(saved.get("win", 0) or 0)
    saved_losses = int(saved.get("loss", 0) or 0)
    current_mmr = int(user_info.get("mmr", {}).get(role, 0) or 0)

    if total_games <= 0:
        return {
            "role": role, "games": 0, "wins": 0, "losses": 0,
            "history_games": 0, "prehistory_games": 0, "current_mmr": current_mmr,
            "start_mmr": 0, "source": "미배치", "error": 0,
        }

    history_entries = get_role_history_entries(gid, uid, role)
    history_games = len(history_entries)
    history_wins = sum(1 for _record, player in history_entries if player.get("result") == "win")
    history_losses = sum(1 for _record, player in history_entries if player.get("result") == "loss")
    first_before = None
    first_time = None
    if history_entries:
        first_record, first_player = history_entries[0]
        first_before = int(first_player.get("before_mmr", current_mmr) or 0)
        first_time = first_record.get("time")

    prehistory_games = max(0, total_games - history_games)
    eval_start = get_role_initial_mmr(user_info, role, None)
    start_mmr = int(eval_start) if eval_start else (first_before if first_before is not None else current_mmr)

    if prehistory_games <= 0:
        wins, losses = history_wins, history_losses
        source = "실기록"
        error = 0
    elif eval_start and first_before is not None:
        estimated = estimate_role_record_range(gid, prehistory_games, start_mmr, first_before)
        wins = int(estimated["wins"]) + history_wins
        losses = int(estimated["losses"]) + history_losses
        source = f"평가점수+실기록(오차 {estimated['error']}점)"
        error = int(estimated["error"])
    elif eval_start:
        estimated = estimate_role_record_range(gid, total_games, start_mmr, current_mmr)
        wins, losses = int(estimated["wins"]), int(estimated["losses"])
        source = f"평가점수 역산(오차 {estimated['error']}점)"
        error = int(estimated["error"])
    elif saved_wins + saved_losses == total_games:
        wins, losses = saved_wins, saved_losses
        source = "저장값 보존"
        error = 0
    else:
        estimated = estimate_role_record_range(gid, total_games, start_mmr, current_mmr)
        wins, losses = int(estimated["wins"]), int(estimated["losses"])
        source = f"점수추정(오차 {estimated['error']}점)"
        error = int(estimated["error"])

    if wins + losses != total_games:
        losses = max(0, total_games - wins)

    return {
        "role": role,
        "games": total_games,
        "wins": wins,
        "losses": losses,
        "history_games": history_games,
        "prehistory_games": prehistory_games,
        "current_mmr": current_mmr,
        "start_mmr": start_mmr,
        "first_history_mmr": first_before,
        "first_history_time": first_time,
        "source": source,
        "error": error,
    }

def remove_uid_from_queue_entries(entries, uid):
    filtered = []
    removed = 0
    for entry in entries:
        user = entry[0] if isinstance(entry, (list, tuple)) and entry else None
        if str(getattr(user, "id", "")) == str(uid):
            removed += 1
            continue
        filtered.append(entry)
    return filtered, removed

def build_tier_graph_entries(gid, uid, line=None, limit=50):
    uid = str(uid)
    records = sorted(get_valid_match_history(gid), key=parse_history_time)
    user_records = []
    last_after_by_role = {}

    for record in records:
        player = next((p for p in record.get('players', []) if str(p.get('user_id')) == uid), None)
        if not player:
            continue

        role = player.get('role')
        before = player.get('before_mmr')
        after = player.get('after_mmr')
        if role not in ROLES or not isinstance(before, int) or not isinstance(after, int):
            continue
        adjusted = role in last_after_by_role and before != last_after_by_role[role]
        user_records.append((record, player, adjusted))
        last_after_by_role[role] = after

    if line:
        entries = []
        for record, player, adjusted in user_records:
            role = player.get('role')
            if role != line:
                continue
            entries.append({
                "time": parse_history_time(record),
                "role": role,
                "result": player.get("result"),
                "delta": player.get("delta", 0),
                "before_score": player.get("before_mmr", 0),
                "score": player.get("after_mmr", 0),
                "adjusted": adjusted,
            })
        return entries[-limit:] if limit and len(entries) > limit else entries

    user_info = bot.user_data.get(gid, {}).get(uid)
    if not isinstance(user_info, dict):
        return []
    user_info = ensure_user_format(user_info)
    role_mmr = dict(user_info.get("mmr", {}))
    reverse_entries = []

    for record, player, adjusted in reversed(user_records):
        values = [score for score in role_mmr.values() if score > 0]
        score = int(sum(values) / len(values)) if values else player.get("after_mmr", 0)
        role_mmr[player.get("role")] = player.get("before_mmr", 0)
        before_values = [score for score in role_mmr.values() if score > 0]
        reverse_entries.append({
            "time": parse_history_time(record),
            "role": player.get("role"),
            "result": player.get("result"),
            "delta": player.get("delta", 0),
            "before_score": int(sum(before_values) / len(before_values)) if before_values else player.get("before_mmr", 0),
            "score": score,
            "adjusted": adjusted,
        })

    entries = list(reversed(reverse_entries))
    if limit and len(entries) > limit:
        entries = entries[-limit:]

    return entries

def make_tier_graph_file(display_name, entries, line=None):
    if not plt or not entries:
        return None

    x_values = list(range(0, len(entries) + 1))
    y_values = [entries[0].get("before_score", entries[0]["score"]), *[entry["score"] for entry in entries]]
    colors = ["#3498db", *[
        "#f1c40f" if entry.get("adjusted") else
        "#2ecc71" if entry.get("result") == "win" else "#e74c3c"
        for entry in entries
    ]]
    role_labels = {
        "탑": "TOP",
        "정글": "JUG",
        "미드": "MID",
        "원딜": "ADC",
        "서폿": "SUP",
    }
    scope = role_labels.get(line, "Overall")

    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=140)
    ax.plot(x_values, y_values, color="#34495e", linewidth=1.8, alpha=0.85)
    ax.scatter(x_values, y_values, c=colors, s=34, edgecolors="#ffffff", linewidths=0.7, zorder=3)
    ax.set_title(f"MMR Trend - {scope}", fontsize=12, pad=10)
    ax.set_xlabel("Games")
    ax.set_ylabel("Tier")
    if MaxNLocator:
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(True, linestyle="--", alpha=0.3)

    y_min = min(y_values)
    y_max = max(y_values)
    span = max(1, y_max - y_min)
    padding = max(12, int(span * 0.08))
    if span < 50:
        padding = 12
    ax.set_ylim(max(0, y_min - padding), y_max + padding)
    lower, upper = ax.get_ylim()
    tier_ticks = [value for value in range(0, 2800, 100) if lower <= value <= upper]
    tier_ticks.extend(value for value in (2800, 3200, 3600) if lower <= value <= upper)
    if len(tier_ticks) > 10:
        tier_ticks = [value for value in range(0, 3601, 400) if lower <= value <= upper]
    if not tier_ticks:
        tier_ticks = [round((lower + upper) / 2)]
    ax.set_yticks(tier_ticks, labels=[rules.get_tier_abbrev(value) for value in tier_ticks])
    ax.set_xlim(0, max(1, len(entries)))

    placement_handle = ax.scatter([], [], c="#3498db", s=34, label="Placement")
    win_handle = ax.scatter([], [], c="#2ecc71", s=34, label="Win")
    loss_handle = ax.scatter([], [], c="#e74c3c", s=34, label="Loss")
    handles = [placement_handle, win_handle, loss_handle]
    if any(entry.get("adjusted") for entry in entries):
        handles.append(ax.scatter([], [], c="#f1c40f", s=34, label="MMR Adjust"))
    ax.legend(handles=handles, loc="best", frameon=True)
    fig.tight_layout()

    image = io.BytesIO()
    fig.savefig(image, format="png", bbox_inches="tight")
    plt.close(fig)
    image.seek(0)
    return discord.File(image, filename="tier_graph.png")

def get_team_players(record, team_name):
    players = [p for p in record.get('players', []) if p.get('team') == team_name]
    if players or team_name not in ("blue", "red"):
        return players

    # 구형 리그전 기록은 team 값에 blue/red 대신 "3팀" 같은 팀 이름을 저장했다.
    if record.get("mode") not in (LEAGUE_SERIES_MODE_KEY, ARAM_LEAGUE_MODE_KEY):
        return players
    teams = record.get("teams", []) or []
    index = 0 if team_name == "blue" else 1
    if len(teams) <= index:
        return players
    legacy_team = teams[index]
    legacy_name = str(legacy_team.get("name") or "")
    legacy_ids = {str(uid) for uid in legacy_team.get("players", []) or []}
    return [
        player for player in record.get("players", [])
        if player.get("team") == legacy_name or str(player.get("user_id")) in legacy_ids
    ]

def get_match_detail_entry(guild_data, match_id, uid):
    return match_stats.get_store(guild_data).get(str(match_id), {}).get(str(uid))

def format_match_detail_suffix(entry, awards, uid):
    if not entry:
        return ""

    parts = []
    champion = str(entry.get("champion") or "").strip()
    if champion:
        parts.append(f"**{champion}**")

    if all(key in entry for key in ("kills", "deaths", "assists")):
        parts.append(f"`{entry.get('kills', 0)}/{entry.get('deaths', 0)}/{entry.get('assists', 0)}`")

    award_marks = []
    if str((awards.get("mvp") or {}).get("user_id")) == str(uid):
        award_marks.append("MVP")
    if str((awards.get("ace") or {}).get("user_id")) == str(uid):
        award_marks.append("ACE")
    if award_marks:
        parts.append("🏅 " + "/".join(award_marks))

    return f"\n└ {' · '.join(parts)}" if parts else ""

def format_match_history_player_line(guild, gid, player, detail, award_marker=""):
    uid = player.get("user_id")
    role = str((detail or {}).get("role") or player.get("role") or "").strip() or "라인"
    champion = str((detail or {}).get("champion") or "").strip() or "챔피언 미입력"

    if detail and all(key in detail for key in ("kills", "deaths", "assists")):
        kda = f"{detail.get('kills', 0)}/{detail.get('deaths', 0)}/{detail.get('assists', 0)}"
    else:
        kda = "-/-/-"

    name = compact_riot_name(get_registered_display_name(guild, gid, uid))
    before_mmr = player.get("lineup_mmr", player.get("before_mmr"))
    try:
        tier_emoji = get_tier_emoji(get_tier_name(int(before_mmr)), guild, gid)
    except (TypeError, ValueError):
        tier_emoji = "❔"

    champion_marker = get_champion_display_marker(champion, guild, gid)
    if champion_marker != champion and champion_marker.startswith("<"):
        champion_display = champion_marker.split(" ", 1)[0]
    else:
        champion_display = champion

    marker = f" {award_marker}" if award_marker else ""
    return (
        f"**{role}**　{tier_emoji} {champion_display} · "
        f"**{discord.utils.escape_markdown(name)}**{marker} · `{kda}`"
    )

def format_match_record_lines(guild, gid, record):
    mode = record.get("mode", "classic")
    if mode == EVENT_MODE_KEY:
        lines = []
        for team in record.get("teams", []):
            team_name = team.get("name", "아레나 팀")
            members = [get_registered_display_name(guild, gid, uid) for uid in team.get("players", [])]
            marker = " 🏆" if record.get("winner") == team_name else ""
            lines.append(f"**{team_name}{marker}** · " + ", ".join(members))
        return lines

    if mode == ARAM_MODE_KEY:
        lines = []
        for team_name in ("blue", "red"):
            members = [
                get_registered_display_name(guild, gid, player.get("user_id"))
                for player in get_team_players(record, team_name)
            ]
            lines.append("\n".join(members) if members else "기록 없음")
        return lines

    guild_data = bot.user_data.setdefault(gid, {})
    match_id = record.get("id")
    awards = match_stats.score_match_awards(guild_data, match_id) if match_id else {}
    mvp_uid = str((awards.get("mvp") or {}).get("user_id") or "")
    ace_uid = str((awards.get("ace") or {}).get("user_id") or "")
    role_order = {role: idx for idx, role in enumerate(ROLES)}

    lines = []
    for team_name in ("blue", "red"):
        team_players = list(get_team_players(record, team_name))
        team_players.sort(
            key=lambda p: role_order.get(
                str(
                    (get_match_detail_entry(guild_data, match_id, p.get("user_id")) or {}).get("role")
                    or p.get("role")
                    or ""
                ).strip(),
                len(ROLES),
            )
        )

        members = []
        for player in team_players:
            uid = player.get("user_id")
            detail = get_match_detail_entry(guild_data, match_id, uid)
            uid_text = str(uid)
            award_marker = "🥇" if uid_text == mvp_uid else ("🛡️" if uid_text == ace_uid else "")
            members.append(
                format_match_history_player_line(
                    guild, gid, player, detail, award_marker=award_marker
                )
            )
        lines.append("\n".join(members) if members else "기록 없음")
    return lines

def format_match_history_award_line(guild, gid, match_id, award):
    if not award:
        return "기록 없음"

    name = compact_riot_name(get_registered_display_name(guild, gid, award.get("user_id")))
    detail = get_match_detail_entry(bot.user_data.setdefault(gid, {}), match_id, award.get("user_id"))
    source = detail or award
    role = str(source.get("role") or "라인").strip()
    champion = str(source.get("champion") or "챔피언 미입력").strip()
    if all(key in source for key in ("kills", "deaths", "assists")):
        kda = f"{source.get('kills', 0)} / {source.get('deaths', 0)} / {source.get('assists', 0)}"
    else:
        kda = "- / - / -"
    return f"`[{name}]` · [{role}] {champion} ({kda})"

def get_user_match_records(gid, uid, role=None):
    uid = str(uid)
    role = str(role or "").strip()
    entries = []
    records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
    guild_data = bot.user_data.setdefault(gid, {})
    for match_rank, record in enumerate(records, 1):
        player = next((p for p in record.get("players", []) if str(p.get("user_id")) == uid), None)
        if not player:
            continue
        detail = get_match_detail_entry(guild_data, record.get("id"), uid)
        entry_role = str((detail or {}).get("role") or player.get("role") or "").strip()
        if role and entry_role != role:
            continue
        entries.append((match_rank, record, player, detail))
    return entries

def format_user_match_history_line(match_rank, record, player, detail):
    role = str((detail or {}).get("role") or player.get("role") or "").strip()
    role_text = f"[{role}] " if role else ""
    result = str(player.get("result") or "").strip()
    result_text = "승 " if result == "win" else "패 " if result == "loss" else ""
    champion = str((detail or {}).get("champion") or "").strip() or "챔피언 미입력"
    if detail and all(key in detail for key in ("kills", "deaths", "assists")):
        kda = f"{detail.get('kills', 0)} / {detail.get('deaths', 0)} / {detail.get('assists', 0)}"
    else:
        kda = "- / - / -"
    return f"Match {match_rank} {result_text}{role_text}{champion} [ {kda} ]"

def build_user_match_history_embed(gid, target, entries, page=1, page_size=5, role=None):
    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    page = max(1, min(int(page or 1), total_pages))
    start = (page - 1) * page_size
    page_entries = entries[start:start + page_size]

    role_text = f" [{role}]" if role else ""
    embed = discord.Embed(
        title=f"📜 {target.display_name}{role_text} 최근 경기",
        color=0x95a5a6,
    )
    if not page_entries:
        embed.description = "📭 아직 기록된 경기가 없습니다."
        return embed

    lines = [
        format_user_match_history_line(match_rank, record, player, detail)
        for match_rank, record, player, detail in page_entries
    ]
    embed.description = "\n".join(lines)
    embed.set_footer(text=f"{page}/{total_pages}페이지 · 최대 5개씩 표시")
    return embed

def summarize_match_period(gid, start_time, guild=None):
    summary = {
        'total': 0,
        'classic': 0,
        'event': 0,
        'noban': 0,
        'participation': defaultdict(int),
        'point_delta': defaultdict(int),
    }

    for record in get_valid_match_history(gid):
        record_time = parse_history_time(record)
        if not record_time or record_time < start_time:
            continue

        summary['total'] += 1
        if record.get('mode') == NOBAN_MODE_KEY:
            summary['noban'] += 1
        elif record.get('mode') in (EVENT_MODE_KEY, ARAM_MODE_KEY, LEAGUE_MODE_KEY):
            summary['event'] += 1
        else:
            summary['classic'] += 1

        seen_users = set()
        for player in record.get('players', []):
            uid = str(player.get('user_id'))
            if not uid or uid == 'None':
                continue
            if guild is not None:
                getter = getattr(guild, 'get_member', None)
                if callable(getter):
                    try:
                        if getter(int(uid)) is None:
                            continue
                    except (TypeError, ValueError):
                        continue
            seen_users.add(uid)
            delta = player.get('delta')
            if isinstance(delta, int):
                summary['point_delta'][uid] += delta

        for uid in seen_users:
            summary['participation'][uid] += 1

    return summary

def format_top_counter(counter, guild, gid, empty_text, reverse=True):
    if not counter:
        return empty_text

    uid, value = sorted(counter.items(), key=lambda item: item[1], reverse=reverse)[0]
    if value == 0:
        return empty_text
    name = discord.utils.escape_markdown(str(get_registered_display_name(guild, gid, uid)))
    return f"`{name}` · **{value:+}점**" if isinstance(value, int) else f"`{name}` · **{value}회**"

def format_top_participants(counter, guild, gid):
    if not counter:
        return "기록 없음"

    top_items = sorted(counter.items(), key=lambda item: item[1], reverse=True)[:3]
    return "\n".join(
        f"**{idx}위** `{discord.utils.escape_markdown(str(get_registered_display_name(guild, gid, uid)))}` · {count}경기"
        for idx, (uid, count) in enumerate(top_items, 1)
    )

def normalize_queue_entry(data):
    user = data[0]
    joined_at = data[1] if len(data) > 1 else time.time()
    pref1 = data[2] if len(data) > 2 else None
    pref2 = data[3] if len(data) > 3 else None
    pref3 = data[4] if len(data) > 4 else None
    return user, joined_at, pref1, pref2, pref3

def is_low_tier_force_entry(data):
    return len(data) > 5 and data[5] == "force_lowtier"

def get_requested_roles(*prefs):
    return [pref for pref in prefs if pref]

def get_playable_roles(user_info):
    user_info = ensure_user_format(user_info)
    return [role for role in ROLES if user_info['mmr'].get(role, 0) > 0]

def get_low_tier_roles(user_info):
    user_info = ensure_user_format(user_info)
    return [
        role for role in ROLES
        if 0 < user_info['mmr'].get(role, 0) <= LOW_TIER_MMR_LIMIT
    ]

def get_low_tier_ineligible_requested_roles(user_info, *prefs):
    user_info = ensure_user_format(user_info)
    return [
        role for role in get_requested_roles(*prefs)
        if user_info['mmr'].get(role, 0) > LOW_TIER_MMR_LIMIT
    ]

def get_low_tier_effective_roles(user_info, *prefs):
    requested = get_requested_roles(*prefs)
    return requested if requested else get_low_tier_roles(user_info)

def get_noban_mmr(user_info):
    user_info = ensure_user_format(user_info)
    return int(user_info.get('noban_mmr', 0) or 0)

def get_noban_rating_source(user_info, role):
    user_info = ensure_user_format(user_info)
    if get_noban_mmr(user_info) > 0:
        return "noban"
    if role in ROLES and int(user_info['mmr'].get(role, 0) or 0) > 0:
        return "normal"
    return None

def get_noban_queue_score(user_info, role):
    source = get_noban_rating_source(user_info, role)
    if source == "noban":
        return get_noban_mmr(user_info)
    if source == "normal":
        return int(user_info['mmr'].get(role, 0) or 0)
    return 0

def get_noban_effective_roles(user_info, *prefs):
    user_info = ensure_user_format(user_info)
    requested = get_requested_roles(*prefs)
    if get_noban_mmr(user_info) > 0:
        return requested if requested else list(ROLES)
    if requested:
        return [role for role in requested if user_info['mmr'].get(role, 0) > 0]
    return get_playable_roles(user_info)

def get_noban_queue_display_mmr(user_info, *prefs):
    user_info = ensure_user_format(user_info)
    if get_noban_mmr(user_info) > 0:
        return get_noban_mmr(user_info)
    scores = [user_info['mmr'].get(role, 0) for role in get_noban_effective_roles(user_info, *prefs)]
    scores = [score for score in scores if score > 0]
    return round(sum(scores) / len(scores)) if scores else 0

def get_unrated_requested_roles(user_info, *prefs):
    user_info = ensure_user_format(user_info)
    return [
        role for role in get_requested_roles(*prefs)
        if user_info['mmr'].get(role, 0) <= 0
    ]

def format_mmr_eval_required_message(roles=None, subject=None):
    role_list = [role for role in (roles or []) if role]
    prefix = f"{subject}님은 " if subject else ""
    if role_list:
        return f"⚠️ {prefix}`{', '.join(role_list)}` 배치가 필요합니다. 관리자에게 `MMR평가`를 요청하세요."
    return f"⚠️ {prefix}신청 가능한 라인 배치가 필요합니다. 관리자에게 `MMR평가`를 요청하세요."

def get_effective_queue_roles(user_info, *prefs):
    requested = get_requested_roles(*prefs)
    return requested if requested else get_playable_roles(user_info)

def get_queue_display_mmr(user_info, *prefs):
    user_info = ensure_user_format(user_info)
    roles = get_effective_queue_roles(user_info, *prefs)
    if roles:
        scores = [user_info['mmr'].get(role, 0) for role in roles if user_info['mmr'].get(role, 0) > 0]
        if scores:
            return round(sum(scores) / len(scores))
    return get_avg_mmr(user_info['mmr'])

def get_low_tier_queue_display_mmr(user_info, *prefs):
    user_info = ensure_user_format(user_info)
    roles = get_low_tier_effective_roles(user_info, *prefs)
    if roles:
        scores = [user_info['mmr'].get(role, 0) for role in roles if user_info['mmr'].get(role, 0) > 0]
        if scores:
            return round(sum(scores) / len(scores))
    return 0

def is_fixed_lane(*prefs):
    return len(set(get_requested_roles(*prefs))) == 1

def is_effectively_fixed_lane(user_info, *prefs):
    return len(set(get_effective_queue_roles(user_info, *prefs))) == 1

def format_pref_text(*prefs):
    requested = get_requested_roles(*prefs)
    return "/".join(requested) if requested else "올라운더"

def format_queue_pref_text(user_info, *prefs):
    requested = get_requested_roles(*prefs)
    if requested:
        return "/".join(requested)

    playable = get_playable_roles(user_info)
    if not playable:
        return "배치 없음"

    # 지망을 직접 선택하지 않았을 때는 실제 배치받은 라인만 표시한다.
    # 5포지션 모두 배치된 유저만 ALL로 표시.
    if set(playable) == set(ROLES):
        return "ALL"
    return "/".join(playable)

def format_low_tier_queue_pref_text(user_info, *prefs):
    requested = get_requested_roles(*prefs)
    if requested:
        return "/".join(requested)

    low_tier_roles = get_low_tier_roles(user_info)
    if low_tier_roles:
        return f"저티어 올라운더({ '/'.join(low_tier_roles) })"
    return "저티어 가능 라인 없음"

def validate_distinct_prefs(*prefs):
    requested = get_requested_roles(*prefs)
    return len(requested) == len(set(requested))

def make_lane_distribution_text(line_counts, fixed_counts, line_score_totals, line_score_counts, candidate_counts=None, flex_count=0, guild=None, gid=None):
    rows = []
    for role in ROLES:
        count = line_counts.get(role, 0)
        fixed = fixed_counts.get(role, 0)
        avg_score = (
            round(line_score_totals.get(role, 0) / line_score_counts.get(role, 0))
            if line_score_counts.get(role, 0)
            else None
        )
        if count <= 0:
            continue
        avg_text = (
            f"평균 {format_public_mmr(avg_score, guild, gid, with_emoji=False)}"
            if avg_score is not None
            else "평균 -"
        )
        if count < 2:
            status = f"부족 {2 - count}"
        elif count == 2:
            status = "충족"
        else:
            status = f"여유 +{count - 2}"
        rows.append(f"`{role}` **{count}/2** · {status} · {avg_text} · 고정 {fixed}명")

    fixed_total = sum(fixed_counts.values())
    summary = f"한 라인만 신청 **{fixed_total}명** · 다지망/올라운더 **{flex_count}명"
    return ("\n".join(rows) + f"\n{summary}") if rows else f"표시할 고정/강제 배정 라인이 없습니다.\n{summary}"

def build_queue_matchability_warning(gid, queue_key, pressure_entries, guild=None):
    """현재 신청자만으로 피할 수 없는 라인 부족/제외급 격차를 안내한다."""
    if queue_key not in (1, 2, 3, 4, 5, NOBAN_QUEUE_NUM, LOW_TIER_QUEUE_KEY):
        return ""

    issues = []
    gap_limit = get_base_lane_exclusion_gap(gid)
    for role in ROLES:
        candidates = []
        for entry in pressure_entries:
            if role not in entry.get("roles", []):
                continue
            score = int(entry.get("scores", {}).get(role, 0) or 0)
            if score > 0:
                candidates.append(score)

        if len(candidates) < 2:
            issues.append(f"• **{role}** · 신청 가능 **{len(candidates)}명** → 최소 2명 필요")
            continue

        candidates.sort()
        pair_gaps = [
            candidates[j] - candidates[i]
            for i in range(len(candidates))
            for j in range(i + 1, len(candidates))
        ]
        min_gap = min(pair_gaps) if pair_gaps else 0
        if min_gap >= gap_limit:
            low = format_public_mmr(candidates[0], guild, gid, with_emoji=False)
            high = format_public_mmr(candidates[-1], guild, gid, with_emoji=False)
            issues.append(
                f"• **{role}** · 후보 {len(candidates)}명 전 조합이 제외급 격차 "
                f"(최소 **{min_gap}점**, 기준 {gap_limit}점 · {low}~{high})"
            )

    if not issues:
        return ""
    queue_name = (
        f"{queue_key}번 큐"
        if isinstance(queue_key, int) and queue_key in (1, 2, 3, 4, 5)
        else get_queue_label(queue_key)
    )
    return (
        f"⚠️ **{queue_name} 현재 대기열 매칭 제약**\n"
        + "\n".join(issues)
        + "\n→ 해당 라인 추가 신청이나 다지망 신청이 필요합니다."
    )

def get_queue_entry_effective_roles(num, data, user_info, pref1, pref2, pref3):
    if num == LOW_TIER_QUEUE_KEY and not is_low_tier_force_entry(data):
        return get_low_tier_effective_roles(user_info, pref1, pref2, pref3)
    if num == NOBAN_QUEUE_NUM:
        return get_noban_effective_roles(user_info, pref1, pref2, pref3)
    return get_effective_queue_roles(user_info, pref1, pref2, pref3)

def get_queue_role_score(num, data, user_info, role):
    if num == NOBAN_QUEUE_NUM:
        return get_noban_queue_score(user_info, role)
    return int(user_info['mmr'].get(role, 0) or 0)

def build_queue_lane_pressure(entries):
    assignments = []
    for entry in entries:
        roles = [role for role in entry["roles"] if role in ROLES]
        if not roles:
            continue
        assignments.append({**entry, "remaining": set(roles), "assigned": None})

    changed = True
    while changed:
        changed = False
        counts = {role: 0 for role in ROLES}
        for item in assignments:
            if item["assigned"]:
                counts[item["assigned"]] += 1

        full_roles = {role for role, count in counts.items() if count >= 2}
        for item in assignments:
            if item["assigned"]:
                continue
            before = set(item["remaining"])
            if len(item["remaining"]) > 1:
                item["remaining"] -= full_roles
            if not item["remaining"]:
                item["remaining"] = before
            if len(item["remaining"]) == 1:
                item["assigned"] = next(iter(item["remaining"]))
                changed = True

    line_counts = {role: 0 for role in ROLES}
    fixed_counts = {role: 0 for role in ROLES}
    line_score_totals = {role: 0 for role in ROLES}
    line_score_counts = {role: 0 for role in ROLES}
    flex_count = 0

    for item in assignments:
        assigned = item["assigned"]
        if assigned:
            line_counts[assigned] += 1
            line_score_totals[assigned] += item["scores"].get(assigned, 0)
            line_score_counts[assigned] += 1
            if len(item["roles"]) == 1:
                fixed_counts[assigned] += 1
        else:
            flex_count += 1

    return line_counts, fixed_counts, line_score_totals, line_score_counts, flex_count

def format_queue_status_player_line(idx, user, user_info, tier_emoji, rating, pref_text):
    title = format_lineup_title_badge(user_info)
    uid = str(getattr(user, "id", ""))
    fallback = getattr(user, "display_name", f"UID {uid}")
    riot_name = compact_riot_name(get_saved_lol_name(str(getattr(getattr(user, "guild", None), "id", "")), uid, fallback))
    if not riot_name:
        riot_name = compact_riot_name(user_info.get("lol_name", "")) or fallback
    riot_name = discord.utils.escape_markdown(str(riot_name))
    position_text = str(pref_text or "배치 없음").strip()
    line = f"`#{idx:02d}` {tier_emoji} **{riot_name}**  ({position_text})"
    if title:
        line += f"\n└ 🏷️ {title}"
    return line


def make_queue_progress_bar(count, required_count):
    """Five-cell queue bar. One half-cell is roughly 10% progress."""
    if required_count <= 0:
        return "□□□□□"
    ratio = max(0.0, min(1.0, float(count) / float(required_count)))
    half_units = min(10, max(0, int(ratio * 10 + 0.5)))
    full = half_units // 2
    half = half_units % 2
    empty = 5 - full - half
    return "■" * full + ("▣" if half else "") + "□" * empty

get_avg_mmr = rules.get_avg_mmr

get_peak_mmr = rules.get_peak_mmr

get_most_played = rules.get_most_played

get_most_played_role = rules.get_most_played_role

get_peak_role_mmr = rules.get_peak_role_mmr

def update_peak_records(user_info):
    user_info = ensure_user_format(user_info)
    peak_records = user_info.setdefault('peak_records', {})

    current_streak = int(user_info.get('streak', 0) or 0)
    if current_streak > int(peak_records.get('best_streak', 0) or 0):
        peak_records['best_streak'] = current_streak

    peak_role, peak_mmr = get_peak_role_mmr(user_info.get('mmr', {}))
    if peak_mmr > int(peak_records.get('best_mmr', 0) or 0):
        peak_records['best_mmr_role'] = peak_role
        peak_records['best_mmr'] = int(peak_mmr)
    return peak_records

get_short_tier_name = rules.get_short_tier_name

get_tier_abbrev = rules.get_tier_abbrev

get_tier_name = rules.get_tier_name

get_tier_order_index = rules.get_tier_order_index

format_tier_short = rules.format_tier_short

is_severe_lane_tier_gap = rules.is_severe_lane_tier_gap

def build_match_quality_warning(matchups, gid=None):
    severe_gap_lines = []
    tier_gap_lines = []
    by_role = {matchup.get("role"): matchup for matchup in matchups}

    def team_label(team_key):
        return "블루팀" if team_key == "BLUE" else "레드팀"

    if matchups:
        blue_avg = int(sum(int(item.get("blue_mmr", 0) or 0) for item in matchups) / len(matchups))
        red_avg = int(sum(int(item.get("red_mmr", 0) or 0) for item in matchups) / len(matchups))
    else:
        blue_avg = red_avg = 0
    team_gap = blue_avg - red_avg
    is_team_balanced = abs(team_gap) <= 80

    for matchup in matchups:
        role = matchup.get("role", "라인")
        blue_mmr = int(matchup.get("blue_mmr", 0) or 0)
        red_mmr = int(matchup.get("red_mmr", 0) or 0)
        gap = abs(blue_mmr - red_mmr)
        blue_scores = [int(by_role.get(item, {}).get("blue_mmr", 0) or 0) for item in ROLES]
        red_scores = [int(by_role.get(item, {}).get("red_mmr", 0) or 0) for item in ROLES]
        gap_limit = get_lane_exclusion_limit(role, blue_scores, red_scores, gid)
        if gap < gap_limit:
            continue

        stronger = "BLUE" if blue_mmr > red_mmr else "RED"
        weaker = "RED" if stronger == "BLUE" else "BLUE"
        stronger_label = matchup.get("blue_label" if stronger == "BLUE" else "red_label", stronger)
        weaker_label = matchup.get("red_label" if stronger == "BLUE" else "blue_label", weaker)

        counter_roles = []
        for other in matchups:
            other_role = other.get("role")
            if other_role == role:
                continue
            other_blue = int(other.get("blue_mmr", 0) or 0)
            other_red = int(other.get("red_mmr", 0) or 0)
            other_gap = other_blue - other_red
            if weaker == "BLUE" and other_gap >= LANE_ADVANTAGE_THRESHOLD:
                counter_roles.append((other_role, other_gap))
            elif weaker == "RED" and other_gap <= -LANE_ADVANTAGE_THRESHOLD:
                counter_roles.append((other_role, abs(other_gap)))
        counter_roles.sort(key=lambda item: item[1], reverse=True)

        if counter_roles:
            counter_text = ", ".join(f"**{counter_role}**" for counter_role, _ in counter_roles[:2])
            play_note = f"{team_label(weaker)}이 크게 이기는 {counter_text} 쪽을 이용해 {role} 격차를 좁혀보세요."
        else:
            play_note = f"{team_label(weaker)} 쪽에서 우세한 다른 라인을 만들기 어려워, {role} 라인전 체감 차이가 더 크게 느껴질 수 있습니다."

        if is_team_balanced:
            balance_note = "팀 평균은 비교적 맞지만,"
        else:
            balance_note = "팀 평균과 별개로,"
        threshold_note = (
            f" 고점 원딜이 포함된 바텀이라 서폿 기준을 {gap_limit}점으로 더 엄격하게 적용했습니다."
            if role == "서폿" and gap_limit < LANE_EXCLUSION_GAP
            else ""
        )
        severe_gap_lines.append(
            f"**{role} 원본 점수차 {gap}점** · 양팀 {role} 라이너의 차이가 매우 큽니다.\n"
            f"{balance_note} {role}은 제외급 격차입니다.{threshold_note}\n"
            f"그래도 이 라인업으로 진행한다면 {team_label(weaker)} 입장에서는 {role}에서 실제로 느끼는 체감 차이가 클 수 있으니, {play_note}"
        )

    adc_matchup = by_role.get("원딜")
    support_matchup = by_role.get("서폿")
    if adc_matchup and support_matchup:
        blue_bot = int(adc_matchup.get("blue_mmr", 0) or 0) + int(support_matchup.get("blue_mmr", 0) or 0)
        red_bot = int(adc_matchup.get("red_mmr", 0) or 0) + int(support_matchup.get("red_mmr", 0) or 0)
        bot_gap = abs(blue_bot - red_bot)
        if bot_gap >= get_bot_duo_exclusion_gap(gid):
            stronger = "BLUE" if blue_bot > red_bot else "RED"
            weaker = "RED" if stronger == "BLUE" else "BLUE"
            counter_roles = []
            for other in matchups:
                other_role = other.get("role")
                if other_role in ("원딜", "서폿"):
                    continue
                other_gap = int(other.get("blue_mmr", 0) or 0) - int(other.get("red_mmr", 0) or 0)
                if weaker == "BLUE" and other_gap >= LANE_ADVANTAGE_THRESHOLD:
                    counter_roles.append((other_role, other_gap))
                elif weaker == "RED" and other_gap <= -LANE_ADVANTAGE_THRESHOLD:
                    counter_roles.append((other_role, abs(other_gap)))
            counter_roles.sort(key=lambda item: item[1], reverse=True)
            if counter_roles:
                counter_text = ", ".join(f"**{counter_role}**" for counter_role, _ in counter_roles[:2])
                play_note = f"{team_label(weaker)}이 크게 이기는 {counter_text} 쪽을 이용해 바텀 격차를 좁혀보세요."
            else:
                play_note = f"{team_label(weaker)} 쪽에서 우세한 다른 라인을 만들기 어려워, 바텀 체감 차이가 더 크게 느껴질 수 있습니다."
            balance_note = "팀 평균은 비교적 맞지만," if is_team_balanced else "팀 평균과 별개로,"
            severe_gap_lines.append(
                f"**봇듀오 원본 합산차 {bot_gap}점** · 양팀 바텀 듀오의 차이가 매우 큽니다.\n"
                f"{balance_note} 봇듀오는 제외급 격차입니다.\n"
                f"그래도 이 라인업으로 진행한다면 {team_label(weaker)} 입장에서는 바텀에서 실제로 느끼는 체감 차이가 클 수 있으니, {play_note}"
            )

    for matchup in matchups:
        blue_mmr = matchup.get("blue_mmr", 0)
        red_mmr = matchup.get("red_mmr", 0)
        if not is_severe_lane_tier_gap(blue_mmr, red_mmr):
            continue

        blue_tier = get_tier_name(blue_mmr)
        red_tier = get_tier_name(red_mmr)
        blue_idx = get_tier_order_index(blue_tier)
        red_idx = get_tier_order_index(red_tier)
        if blue_idx <= red_idx:
            low_label = matchup.get("blue_label", "BLUE")
            low_tier = blue_tier
            high_label = matchup.get("red_label", "RED")
            high_tier = red_tier
        else:
            low_label = matchup.get("red_label", "RED")
            low_tier = red_tier
            high_label = matchup.get("blue_label", "BLUE")
            high_tier = blue_tier

        tier_gap_lines.append(
            f"**{matchup.get('role', '라인')}** · {low_label} ({format_tier_short(low_tier)}) ↔ {high_label} ({format_tier_short(high_tier)})"
        )

    if not severe_gap_lines and not tier_gap_lines:
        return None

    detail_sections = []
    if severe_gap_lines:
        detail_sections.append("**제외급 격차 라인**\n" + "\n\n".join(severe_gap_lines))
    if tier_gap_lines:
        detail_sections.append("**티어 격차 발생 라인**\n" + "\n".join(tier_gap_lines))

    return (
        "현재 라인업에서 일부 맞라인 간 전력 차이가 크게 확인되었습니다.\n"
        "팀 평균이 맞더라도 특정 라인은 라인전 단계부터 경기 흐름이 한쪽으로 기울 가능성이 있습니다.\n\n"
        + "\n\n".join(detail_sections)
        + "\n\n그대로 진행해도 팀 평균 밸런스는 허용 범위로 판단될 수 있지만, 더 원활한 경기를 원한다면 `/리셋` 후 포지션을 다시 조정해 재라인업하는 것을 권장합니다."
    )




















async def get_bot_application_id():
    application_id = getattr(bot, "application_id", None)
    if application_id:
        return application_id
    app_info = await bot.application_info()
    return app_info.id

async def clear_global_slash_commands():
    application_id = await get_bot_application_id()
    await bot.http.bulk_upsert_global_commands(application_id, [])
    print("✅ 슬래시 명령 글로벌 목록 비움")

def build_slash_command_payload():
    return [command.to_dict(bot.tree) for command in bot.tree.get_commands(guild=None)]

def get_slash_payload_fingerprint(payload):
    try:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        raw = str(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

async def restore_active_games_safely(guild):
    """Restore persisted active-game snapshots without blocking startup."""
    gid = str(guild.id)
    if not isinstance(getattr(bot, "active_games", None), dict):
        bot.active_games = {}
    if not ACTIVE_GAME_STORAGE_READY:
        bot.active_games.setdefault(gid, {})
        logger.warning(
            "진행 게임 복구 건너뜀: lucidgame_storage.py가 이전 버전입니다. guild=%s",
            gid,
        )
        return 0, 0
    active_restore_ready = getattr(bot, "active_restore_ready", None)
    if active_restore_ready is None:
        active_restore_ready = set()
        bot.active_restore_ready = active_restore_ready
    active_restore_in_progress = getattr(bot, "active_restore_in_progress", None)
    if active_restore_in_progress is None:
        active_restore_in_progress = set()
        bot.active_restore_in_progress = active_restore_in_progress
    if gid in active_restore_ready:
        return len(bot.active_games.get(gid) or {}), 0
    if gid in active_restore_in_progress:
        return 0, 0

    active_restore_in_progress.add(gid)
    try:
        raw_snapshot = bot.user_data.get(gid, {}).get(ACTIVE_GAMES_KEY)
        if not isinstance(raw_snapshot, dict):
            bot.active_games.setdefault(gid, {})
            active_restore_ready.add(gid)
            return 0, 0

        member_ids = storage.collect_member_ids(raw_snapshot)
        members = {}
        missing_member_ids = set()
        for raw_uid in member_ids:
            uid = str(raw_uid or "").strip()
            if not uid or uid in members or uid in missing_member_ids:
                continue
            try:
                member = guild.get_member(int(uid)) if hasattr(guild, "get_member") else None
            except (TypeError, ValueError):
                member = None
            if member is None and hasattr(guild, "fetch_member"):
                try:
                    member = await guild.fetch_member(int(uid))
                except Exception:
                    member = None
            if member is None:
                missing_member_ids.add(uid)
            else:
                members[uid] = member

        def resolve_member(uid):
            return members.get(str(uid))

        restored_states = {}
        dropped_entries = 0
        for raw_queue_key, raw_state in raw_snapshot.items():
            try:
                queue_key = rules.deserialize_queue_key(raw_queue_key)
            except Exception:
                logger.warning("진행 게임 큐 키 복원 실패: guild=%s queue=%s", gid, raw_queue_key)
                continue
            if queue_key in (LEAGUE_SIM_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY):
                continue
            if not isinstance(raw_state, dict):
                logger.warning("진행 게임 스냅샷 형식 무시: guild=%s queue=%s", gid, queue_key)
                continue
            state = storage.restore_active_game_value(raw_state, resolve_member)
            if state is storage._MISSING_MEMBER or not isinstance(state, dict):
                logger.warning("진행 게임 스냅샷 복원 실패: guild=%s queue=%s", gid, queue_key)
                continue
            raw_queue_snapshot = raw_state.get("queue_snapshot")
            restored_queue_snapshot = state.get("queue_snapshot")
            if isinstance(raw_queue_snapshot, list) and isinstance(restored_queue_snapshot, list):
                dropped_entries += max(0, len(raw_queue_snapshot) - len(restored_queue_snapshot))
            state.setdefault("guild_id", gid)
            state.setdefault("queue_key", str(queue_key))
            state.setdefault("status", "active")
            state.setdefault("created_at", now_kst().strftime("%Y-%m-%d %H:%M:%S"))
            state.setdefault("game_id", f"legacy-{gid}-{queue_key}")

            voice_channels = state.get("voice_channels")
            if isinstance(voice_channels, dict):
                missing_channels = []
                for channel_id in voice_channels.values():
                    try:
                        channel = guild.get_channel(int(channel_id)) if hasattr(guild, "get_channel") else None
                    except (TypeError, ValueError):
                        channel = None
                    if channel is None:
                        missing_channels.append(str(channel_id))
                if missing_channels:
                    logger.warning(
                        "진행 게임 음성 채널 일부 누락(게임 보존): guild=%s queue=%s channel_ids=%s",
                        gid,
                        queue_key,
                        ",".join(missing_channels),
                    )
            restored_states[queue_key] = state

        bot.active_games[gid] = restored_states
        active_restore_ready.add(gid)
        if missing_member_ids or dropped_entries:
            logger.warning(
                "진행 게임 멤버 복원 정리: guild=%s missing=%s dropped_entries=%s",
                gid,
                len(missing_member_ids),
                dropped_entries,
            )
            try:
                bot.save_lucid_data(gid)
            except Exception:
                logger.exception("진행 게임 정리 스냅샷 저장 실패: guild=%s", gid)
        return len(restored_states), len(missing_member_ids)
    except Exception:
        logger.exception("진행 게임 DB 복원 실패: guild=%s; 원본 스냅샷 보존", gid)
        raise
    finally:
        active_restore_in_progress.discard(gid)


async def sync_guild_slash_commands(guild):
    try:
        payload = build_slash_command_payload()
        application_id = await get_bot_application_id()
    except Exception as exc:
        logger.exception("슬래시 명령 payload 생성 실패: guild=%s(%s)", getattr(guild, "name", "unknown"), guild.id)
        print(f"❌ 슬래시 명령 payload 생성 실패: {guild.name}({guild.id}) {type(exc).__name__}: {str(exc)[:500]}")
        return None

    payload_fingerprint = get_slash_payload_fingerprint(payload)

    try:
        synced = await bot.http.bulk_upsert_guild_commands(application_id, guild.id, payload)
        print(f"✅ 슬래시 명령 REST 서버 동기화: {guild.name}({guild.id}) {len(synced)}개")
        bot.slash_sync_failed_payloads.pop(str(guild.id), None)
        return synced
    except Exception as exc:
        bot.slash_sync_failed_payloads[str(guild.id)] = payload_fingerprint
        logger.exception("슬래시 명령 REST 서버 동기화 실패: guild=%s(%s)", getattr(guild, "name", "unknown"), guild.id)
        print(f"❌ 슬래시 명령 REST 서버 동기화 실패: {guild.name}({guild.id}) {type(exc).__name__}: {str(exc)[:500]}")
        return None

@bot.event
async def on_ready():
    # 디스코드 봇 구동 시 슬래시 커맨드 트리 구조를 동기화합니다.
    # 서버별 명령어만 즉시 동기화하고, 중복 노출을 막기 위해 글로벌 명령어는 비웁니다.
    help_check_ok = run_help_guide_coverage_check()
    init_chzzk_link_tables()
    register_participation_panel_views()
    if not getattr(bot, "_feedback_persistent_views_registered", False):
        bot.add_view(FeedbackOperatorActionView())
        bot.add_view(FeedbackUserReplyView())
        bot._feedback_persistent_views_registered = True
    if not bot.command_tree_synced:
        sync_ok = True
        for guild in bot.guilds:
            try:
                if await sync_guild_slash_commands(guild) is None:
                    sync_ok = False
            except Exception as exc:
                sync_ok = False
                logger.exception("슬래시 명령 최종 동기화 실패: guild=%s(%s)", getattr(guild, "name", "unknown"), guild.id)
                print(f"❌ 슬래시 명령 최종 동기화 실패: {guild.name}({guild.id}) {type(exc).__name__}: {str(exc)[:500]}")
        try:
            await clear_global_slash_commands()
        except Exception as exc:
            sync_ok = False
            logger.exception("슬래시 명령 글로벌 비우기 실패")
            print(f"❌ 슬래시 명령 글로벌 비우기 실패: {type(exc).__name__}: {str(exc)[:500]}")
        bot.command_tree_synced = sync_ok
    queue_controller = ensure_queue_controller_instance()
    for index, guild in enumerate(bot.guilds):
        gid = str(guild.id)
        try:
            restored_count, missing_count = await restore_queue_state_safely(guild)
            if restored_count or missing_count:
                logger.info(
                    "대기열 DB 복원 완료: guild=%s restored=%s missing=%s",
                    gid, restored_count, missing_count,
                )
            await restore_active_games_safely(guild)
            match_channel_id = str(bot.user_data.get(gid, {}).get(MATCH_OUTPUT_CHANNEL_KEY) or "")
            match_channel = guild.get_channel(int(match_channel_id)) if match_channel_id.isdigit() else None
            if isinstance(match_channel, (discord.TextChannel, discord.ForumChannel)):
                await apply_function_channel_permissions(match_channel)
            await update_help_guide(guild, gid)
            await update_admin_help_guide(guild, gid)
            await update_streaming_help_guide(guild, gid)
            admin_help_cfg = bot.user_data.get(gid, {}).get(ADMIN_HELP_GUIDE_KEY) or {}
            for admin_help_channel_id in (admin_help_cfg.get("channel_id"), admin_help_cfg.get("forum_channel_id")):
                admin_help_channel_id = str(admin_help_channel_id or "")
                if not admin_help_channel_id.isdigit():
                    continue
                admin_help_channel = guild.get_channel(int(admin_help_channel_id))
                if isinstance(admin_help_channel, (discord.TextChannel, discord.ForumChannel)):
                    await apply_admin_help_channel_permissions(admin_help_channel)
            party_admin_channel_id = str(bot.user_data.get(gid, {}).get(PARTY_ADMIN_CHANNEL_KEY) or "")
            party_admin_channel = guild.get_channel(int(party_admin_channel_id)) if party_admin_channel_id.isdigit() else None
            if isinstance(party_admin_channel, discord.TextChannel):
                await apply_admin_help_channel_permissions(party_admin_channel)
            await refresh_participation_panel(guild, gid)
            await refresh_party_panel(guild, gid)
            await refresh_party_admin_cards(guild, gid)
            await refresh_chzzk_participation_panel(guild, gid)
            await refresh_temp_voice_panel(guild, gid)
            await refresh_report_panel(guild, gid)
            await cleanup_auto_summoner_registration_responses(get_auto_summoner_registration_channel(guild, gid))
            maybe_schedule_patch_summary_promo(gid)
            start_chzzk_listener_if_available(guild)
        except Exception as exc:
            logger.exception("서버 시작 초기화 실패: guild=%s(%s)", getattr(guild, "name", "unknown"), gid)
        if AUTO_GUILD_REFRESH_DELAY_SECONDS > 0 and index < len(bot.guilds) - 1:
            await asyncio.sleep(AUTO_GUILD_REFRESH_DELAY_SECONDS)
    if not bot.ranking_refresh_loop_started:
        daily_ranking_board_refresh.start()
        bot.ranking_refresh_loop_started = True
    if not bot.hourly_ranking_refresh_loop_started:
        hourly_ranking_board_refresh.start()
        bot.hourly_ranking_refresh_loop_started = True
    if not bot.queue_cleanup_loop_started:
        stale_queue_cleanup_loop.start()
        bot.queue_cleanup_loop_started = True
    if not bot.recruitment_lineup_loop_started:
        scheduled_recruitment_lineup_loop.start()
        bot.recruitment_lineup_loop_started = True
    if not bot.chzzk_discovery_loop_started:
        chzzk_listener_discovery_loop.start()
        bot.chzzk_discovery_loop_started = True
    if not bot.coach_discord_notification_loop_started and bot.db_enabled:
        coach_discord_notification_loop.start()
        bot.coach_discord_notification_loop_started = True
    print("==========================================")
    print(f"✅ 시스템 검사 완료")
    print(f"{'✅' if help_check_ok else '⚠️'} 도움말 자체 점검 {'통과' if help_check_ok else '누락 항목 확인 필요'}")
    print(f"✅ 구동 봇 서비스 명칭: {bot.user.name}")
    print(f"✅ 1/2/3지망 밸런스 계산 준비 완료")
    print(f"✅ 연승/연패(±1 추가보정) 시스템 패치 적용 중")

@bot.event
async def on_guild_join(guild):
    gid = str(guild.id)
    try:
        await sync_guild_slash_commands(guild)
    except Exception as exc:
        logger.warning("새 서버 명령어 동기화 실패: guild_id=%s error=%s", gid, exc)

    bot.user_data.setdefault(gid, {})
    try:
        queue_controller = ensure_queue_controller_instance()
        await restore_queue_state_safely(guild)
        await restore_active_games_safely(guild)
        await update_help_guide(guild, gid)
        await update_admin_help_guide(guild, gid)
        await update_streaming_help_guide(guild, gid)
        await refresh_participation_panel(guild, gid)
        await refresh_party_panel(guild, gid)
        await refresh_chzzk_participation_panel(guild, gid)
        await refresh_temp_voice_panel(guild, gid)
        await refresh_report_panel(guild, gid)
        start_chzzk_listener_if_available(guild)
        bot.save_lucid_data(gid)
    except Exception as exc:
        logger.warning("새 서버 초기화 작업 실패: guild_id=%s error=%s", gid, exc)

@bot.event
async def on_member_join(member):
    await send_member_audit_log(member, "join")

@bot.event
async def on_member_remove(member):
    await send_member_audit_log(member, "remove")

def get_auto_summoner_registration_channel(guild, gid=None):
    if not guild:
        return None
    gid = str(gid or guild.id)
    channel_id = bot.user_data.get(gid, {}).get(AUTO_SUMMONER_REGISTRATION_CHANNEL_KEY)
    if not channel_id:
        return None
    try:
        return guild.get_channel(int(channel_id))
    except (TypeError, ValueError):
        return None

async def cleanup_auto_summoner_registration_responses(channel):
    if not channel or not hasattr(channel, "history"):
        return
    try:
        async for recent in channel.history(limit=20):
            if getattr(getattr(recent, "author", None), "id", None) != getattr(bot.user, "id", None):
                continue
            titles = {str(getattr(embed, "title", "") or "") for embed in (getattr(recent, "embeds", []) or [])}
            if titles & {"🔄 소환사 정보 수정 완료", "✅ 신규 소환사 시스템 등록 완료"}:
                await recent.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass

async def handle_auto_summoner_registration_message(message):
    if (
        not message
        or not getattr(message, "guild", None)
        or getattr(getattr(message, "author", None), "bot", False)
    ):
        return False

    gid = str(message.guild.id)
    configured_channel = get_auto_summoner_registration_channel(message.guild, gid)
    if not configured_channel or getattr(message.channel, "id", None) != configured_channel.id:
        return False

    try:
        await cleanup_auto_summoner_registration_responses(message.channel)
        content = str(getattr(message, "content", "") or "").strip()
        if not content:
            logger.error(
                "자동 소환사등록 메시지 내용 수신 실패: guild_id=%s channel_id=%s message_content_intent=%s",
                gid,
                getattr(message.channel, "id", None),
                bool(bot.intents.message_content),
            )
            await message.channel.send(
                f"{message.author.mention} ⚠️ 입력 내용을 읽지 못했습니다. Discord Developer Portal의 Message Content Intent를 확인해주세요.",
                allowed_mentions=discord.AllowedMentions(users=True),
                delete_after=15,
            )
            return True
        if "\n" in content or getattr(message, "attachments", None):
            return True

        summoner_name = normalize_riot_id(content)
        if not summoner_name:
            await message.channel.send(
                f"{message.author.mention} ⚠️ Riot ID를 `닉네임#태그` 형식으로 한 줄에 입력해주세요. 예: `Hide on bush#KR1`",
                allowed_mentions=discord.AllowedMentions(users=True),
                delete_after=15,
            )
            return True

        embed, is_new_registration, dm_status = await register_summoner_profile(message.guild, message.author, summoner_name)
        try:
            await message.channel.send(
                content=message.author.mention,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True),
                delete_after=10,
            )
            if is_new_registration and dm_status:
                await message.channel.send(
                    f"{message.author.mention} {dm_status}",
                    allowed_mentions=discord.AllowedMentions(users=True),
                    delete_after=10,
                )
        except discord.Forbidden:
            logger.warning("자동 소환사등록 응답 권한 부족: guild_id=%s channel_id=%s", gid, getattr(message.channel, "id", None))
        except discord.HTTPException as exc:
            logger.warning("자동 소환사등록 응답 실패: guild_id=%s channel_id=%s error=%s", gid, getattr(message.channel, "id", None), exc)
        return True
    finally:
        if not getattr(getattr(message.author, "guild_permissions", None), "administrator", False):
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                logger.warning("자동 소환사등록 원문 삭제 권한 부족: guild_id=%s channel_id=%s", gid, getattr(message.channel, "id", None))
            except discord.HTTPException as exc:
                logger.warning("자동 소환사등록 원문 삭제 실패: guild_id=%s channel_id=%s error=%s", gid, getattr(message.channel, "id", None), exc)

@bot.event
async def on_message(message):
    if record_chat_message(message):
        pass
    try:
        await handle_auto_summoner_registration_message(message)
    except Exception:
        logger.exception(
            "자동 소환사등록 처리 실패: guild_id=%s channel_id=%s author_id=%s",
            getattr(getattr(message, "guild", None), "id", None),
            getattr(getattr(message, "channel", None), "id", None),
            getattr(getattr(message, "author", None), "id", None),
        )
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    if not member or getattr(member, "bot", False) or not member.guild:
        return
    guild = member.guild
    gid = str(guild.id)
    guild_data = bot.user_data.setdefault(gid, {})
    trigger_id = str(guild_data.get(TEMP_VOICE_TRIGGER_CHANNEL_KEY) or "")

    if after and after.channel and trigger_id and str(after.channel.id) == trigger_id:
        try:
            channel = await create_temp_voice_channel(
                guild,
                gid,
                member,
                category=after.channel.category,
            )
            await member.move_to(channel, reason="방만들기 채널 입장")
        except discord.Forbidden:
            logger.warning("임시 음성방 생성/이동 권한 부족: guild_id=%s member_id=%s", gid, member.id)
        except discord.HTTPException as exc:
            logger.warning("임시 음성방 생성/이동 실패: guild_id=%s member_id=%s error=%s", gid, member.id, exc)

    if before and before.channel:
        await cleanup_temp_voice_channel(guild, gid, before.channel)
    print("==========================================")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    namespace = getattr(interaction, "namespace", None)
    original = getattr(error, "original", error)
    if isinstance(original, discord.HTTPException) and getattr(original, "code", None) in (40060, 10062):
        logger.warning(
            "슬래시 명령 중복/만료 응답 생략: command=%s namespace=%s code=%s",
            interaction.command,
            namespace,
            original.code,
        )
        return
    logger.exception("슬래시 명령 처리 중 오류 발생: command=%s namespace=%s", interaction.command, namespace, exc_info=error)

    if isinstance(error, app_commands.MissingPermissions):
        message = "🚫 이 명령어를 사용할 권한이 부족합니다."
    elif isinstance(error, app_commands.BotMissingPermissions):
        message = "⚠️ 봇 권한이 부족해서 명령을 처리하지 못했습니다."
    else:
        message = "⚠️ 명령을 처리하는 중 문제가 생겼습니다. 운영진은 `/봇제작자문의`로 상황을 보내주세요."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            try:
                await interaction.response.send_message(message, ephemeral=True)
            except discord.HTTPException as send_error:
                if getattr(send_error, "code", None) == 40060:
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    raise
    except discord.NotFound:
        logger.warning("슬래시 명령 오류 안내 생략: interaction token 만료 command=%s namespace=%s", interaction.command, namespace)
    except Exception as send_error:
        logger.exception("슬래시 명령 오류 안내 전송 실패: %s", send_error)

# ==============================================================================
# [1. 내전 시스템 - 일반 소환사 전용 명령어]
# ==============================================================================


























































completion_dm_choices = [
    app_commands.Choice(name="안보내기", value="off"),
    app_commands.Choice(name="보내기", value="send"),
]






queue_choices = (
    [app_commands.Choice(name=f"{i}번 큐", value=str(i)) for i in range(1, 6)]
    + [
        app_commands.Choice(name="노밴 모드", value="노밴 모드"),
        app_commands.Choice(name="저티어 큐", value="저티어 큐"),
        app_commands.Choice(name="아레나(3x6)", value="아레나(3x6)"),
        app_commands.Choice(name=LEAGUE_SERIES_MODE_NAME, value=LEAGUE_SERIES_MODE_NAME),
        app_commands.Choice(name="칼바람 나락", value="칼바람 나락"),
        app_commands.Choice(name=ARAM_LEAGUE_MODE_NAME, value=ARAM_LEAGUE_MODE_NAME),
    ]
)












format_kst_datetime = rules.format_kst_datetime

format_duration_ko = rules.format_duration_ko







parse_iso_datetime = rules.parse_iso_datetime























def format_feedback_user_info(user: discord.abc.User):
    mention = getattr(user, "mention", "알 수 없음")
    username = getattr(user, "name", "unknown")
    discriminator = getattr(user, "discriminator", "0")
    legacy_tag = f"{username}#{discriminator}" if discriminator and discriminator != "0" else username
    global_name = getattr(user, "global_name", None) or getattr(user, "display_name", None) or "-"
    return (
        f"{mention}\n"
        f"친추/검색용: `{legacy_tag}`\n"
        f"표시 이름: `{global_name}`\n"
        f"Discord ID: `{user.id}`"
    )

async def get_feedback_owner():
    owner = bot.get_user(SUPPORT_DM_OWNER_ID)
    if owner:
        return owner
    try:
        return await bot.fetch_user(SUPPORT_DM_OWNER_ID)
    except (discord.NotFound, discord.HTTPException):
        return None

def get_feedback_alert_channel(guild, gid):
    if not guild or not gid:
        return None
    channel_id = str(bot.user_data.get(str(gid), {}).get(FEEDBACK_ALERT_CHANNEL_KEY) or "")
    if not channel_id.isdigit():
        return None
    channel = guild.get_channel(int(channel_id))
    return channel if isinstance(channel, discord.TextChannel) else None

def ensure_feedback_reservation_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS coach_reservations (
                id UUID PRIMARY KEY,
                coach_id TEXT,
                coach_name TEXT NOT NULL,
                coach_category TEXT,
                coach_price TEXT,
                student_name TEXT NOT NULL,
                contact TEXT NOT NULL,
                preferred_time TEXT NOT NULL,
                memo TEXT,
                status TEXT NOT NULL DEFAULT '신규',
                source TEXT NOT NULL DEFAULT 'coach-platform',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            ALTER TABLE coach_reservations
            ADD COLUMN IF NOT EXISTS feedback_metadata JSONB
            """
        )

def save_feedback_reservation_sync(interaction, riot_id, champion_kda, inquiry, attachment):
    if not DATABASE_URL or psycopg is None or Jsonb is None:
        logger.warning("Discord feedback reservation DB save skipped: DATABASE_URL/psycopg unavailable")
        return

    guild = interaction.guild
    channel = interaction.channel
    user = interaction.user
    created_at = datetime.now(timezone.utc)
    display_name = getattr(user, "display_name", None) or getattr(user, "global_name", None) or getattr(user, "name", "unknown")
    username = getattr(user, "name", "unknown")
    discriminator = getattr(user, "discriminator", "0")
    legacy_tag = f"{username}#{discriminator}" if discriminator and discriminator != "0" else username

    attachment_metadata = None
    attachment_line = "ROFL 파일 없음"
    if attachment:
        attachment_metadata = {
            "id": str(getattr(attachment, "id", "")),
            "filename": getattr(attachment, "filename", None),
            "url": getattr(attachment, "url", None),
            "size": getattr(attachment, "size", None),
            "content_type": getattr(attachment, "content_type", None),
        }
        size = getattr(attachment, "size", 0) or 0
        attachment_line = f"ROFL: {attachment_metadata['filename']} ({size / (1024 * 1024):.1f}MB)\nURL: {attachment_metadata['url']}"

    guild_name = getattr(guild, "name", "DM/unknown")
    guild_id = str(getattr(guild, "id", "unknown"))
    channel_name = getattr(channel, "name", None) or str(channel)
    channel_id = str(getattr(channel, "id", "unknown"))
    metadata = {
        "discord_user_id": str(getattr(user, "id", "")),
        "discord_display_name": display_name,
        "discord_username": legacy_tag,
        "guild_id": guild_id,
        "guild_name": guild_name,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "riot_id": riot_id,
        "champion_kda": champion_kda,
        "inquiry": inquiry,
        "attachment": attachment_metadata,
    }
    memo = (
        f"{inquiry}"
    )

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        ensure_feedback_reservation_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO coach_reservations (
                    id,
                    coach_id,
                    coach_name,
                    coach_category,
                    coach_price,
                    student_name,
                    contact,
                    preferred_time,
                    memo,
                    status,
                    source,
                    feedback_metadata,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid.uuid4(),
                    "discord-feedback",
                    "Discord /피드백 접수",
                    "discord-feedback",
                    champion_kda,
                    riot_id,
                    f"{legacy_tag} / Discord ID: {getattr(user, 'id', 'unknown')}",
                    "-",
                    memo[:1200],
                    "신규",
                    "discord-feedback",
                    Jsonb(metadata),
                    created_at,
                    created_at,
                ),
            )

async def save_feedback_reservation_to_coach_db(interaction, riot_id, champion_kda, inquiry, attachment):
    await asyncio.to_thread(save_feedback_reservation_sync, interaction, riot_id, champion_kda, inquiry, attachment)

def get_report_channel(guild, gid):
    if not guild or not gid:
        return None
    channel_id = str(bot.user_data.get(str(gid), {}).get(REPORT_CHANNEL_KEY) or "")
    if not channel_id.isdigit():
        return None
    channel = guild.get_channel(int(channel_id))
    return channel if isinstance(channel, discord.TextChannel) else None


def build_report_number(interaction):
    created_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    interaction_tail = str(getattr(interaction, "id", ""))[-6:]
    return f"R{created_ms}-{interaction_tail or secrets.token_hex(3).upper()}"


@bot.tree.command(name="신고", description="운영진에게 익명 신고를 접수합니다.")
@app_commands.describe(
    대상="신고 대상을 입력해주세요. Discord 이름/@멘션 또는 닉네임#태그 등",
    사유="신고 사유와 상황을 가능한 구체적으로 적어주세요.",
)
async def submit_anonymous_report(
    interaction: discord.Interaction,
    대상: str,
    사유: str,
):
    return await submit_anonymous_report_payload(interaction, 대상, 사유)


async def submit_anonymous_report_payload(interaction: discord.Interaction, 대상: str, 사유: str):
    # 슬래시 명령과 신고 패널이 동일한 접수 로직을 사용한다.
    try:
        await interaction.response.defer(ephemeral=True, thinking=True)
    except discord.NotFound:
        logger.warning(
            "신고 접수 응답 예약 실패: 만료된 인터랙션입니다. guild_id=%s user_id=%s",
            interaction.guild_id,
            getattr(interaction.user, "id", None),
        )
        return

    if not interaction.guild_id or not interaction.guild:
        return await interaction.followup.send("⚠️ 신고는 서버 안에서만 사용할 수 있습니다.", ephemeral=True)

    gid = str(interaction.guild_id)
    target_text = str(대상 or "").strip().replace("\n", " ")
    reason_text = str(사유 or "").strip()
    reason_text = "\n".join(line.rstrip() for line in reason_text.splitlines()).strip()

    if not target_text:
        return await interaction.followup.send("⚠️ 신고 대상을 입력해주세요.", ephemeral=True)
    if not reason_text:
        return await interaction.followup.send("⚠️ 신고 사유를 입력해주세요.", ephemeral=True)

    report_channel = get_report_channel(interaction.guild, gid)
    if report_channel is None:
        return await interaction.followup.send(
            "⚠️ 이 서버에는 신고 접수 채널이 아직 설정되지 않았습니다. 운영진에게 `/채널설정 일반 항목:신고접수(운영진)` 설정을 요청해주세요.",
            ephemeral=True,
        )

    bot_member = interaction.guild.me
    permissions = report_channel.permissions_for(bot_member) if bot_member else None
    if not permissions or not permissions.view_channel or not permissions.send_messages or not permissions.embed_links:
        return await interaction.followup.send(
            "⚠️ 현재 신고 접수 채널에 봇의 메시지 보기/보내기/임베드 권한이 없습니다. 운영진에게 알려주세요.",
            ephemeral=True,
        )

    report_number = build_report_number(interaction)
    created_at = datetime.now(timezone.utc)

    # 신고자 Discord ID는 운영진에게 보이지 않고 내부 중복/악용 대응용 로그에만 저장한다.
    guild_data = bot.user_data.setdefault(gid, {})
    report_log = guild_data.setdefault(REPORT_LOG_KEY, [])
    if not isinstance(report_log, list):
        report_log = []
        guild_data[REPORT_LOG_KEY] = report_log

    report_log.append({
        "report_number": report_number,
        "reporter_id": str(getattr(interaction.user, "id", "")),
        "target": target_text[:500],
        "reason": reason_text[:3000],
        "created_at": created_at.isoformat(),
        "channel_id": str(report_channel.id),
    })
    if len(report_log) > REPORT_LOG_LIMIT:
        del report_log[:-REPORT_LOG_LIMIT]
    bot.save_lucid_data(gid)

    embed = discord.Embed(
        title="🚨 익명 신고 접수",
        color=0xe74c3c,
        timestamp=created_at,
    )
    embed.add_field(name="신고 번호", value=f"`{report_number}`", inline=False)
    embed.add_field(name="대상", value=discord.utils.escape_markdown(target_text[:500]), inline=False)
    embed.add_field(name="사유", value=discord.utils.escape_markdown(reason_text[:3000]), inline=False)
    embed.set_footer(text="신고자 정보는 운영진에게도 표시되지 않습니다.")

    try:
        await report_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
        logger.warning(
            "익명 신고 운영진 채널 전송 실패: guild_id=%s report=%s error=%s",
            gid,
            report_number,
            exc,
        )
        return await interaction.followup.send(
            "⚠️ 신고를 운영진 채널로 전송하지 못했습니다. 잠시 후 다시 시도하거나 운영진에게 알려주세요.",
            ephemeral=True,
        )

    await interaction.followup.send(
        f"✅ 익명 신고가 접수되었습니다.\n신고 번호: `{report_number}`\n"
        "신고자 정보는 운영진에게도 표시되지 않습니다.",
        ephemeral=True,
    )


def normalize_lol_patch_version(value):
    match = re.search(r"(\d+)\.(\d+)", str(value or ""))
    if not match:
        return None
    return f"{int(match.group(1))}.{int(match.group(2))}"


def extract_rofl_client_version(data: bytes):
    if not isinstance(data, (bytes, bytearray)) or len(data) < 0x10 or bytes(data[:4]) != b"RIOT":
        raise ValueError("유효한 LoL .rofl 파일이 아닙니다.")
    version_len = int(data[0x0E])
    if version_len <= 0 or 0x0F + version_len > len(data):
        raise ValueError("ROFL에서 경기 버전을 읽지 못했습니다.")
    try:
        full_version = bytes(data[0x0F:0x0F + version_len]).decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("ROFL 경기 버전 형식이 올바르지 않습니다.") from exc
    patch = normalize_lol_patch_version(full_version)
    if not patch:
        raise ValueError(f"ROFL 경기 버전을 판별하지 못했습니다: {full_version[:80]}")
    return full_version, patch


async def get_current_lol_patch_version():
    versions = await asyncio.to_thread(fetch_url_json, f"{DDRAGON_BASE_URL}/api/versions.json")
    latest_version = str((versions or [""])[0] or "").strip()
    patch = normalize_lol_patch_version(latest_version)
    if not latest_version or not patch:
        raise RuntimeError("현재 LoL 패치 버전을 확인하지 못했습니다.")
    return latest_version, patch


async def validate_feedback_rofl_current_patch(attachment):
    if attachment is None:
        return None
    filename = str(getattr(attachment, "filename", "") or "")
    if not filename.lower().endswith(".rofl"):
        raise ValueError("`.rofl` 리플레이 파일만 업로드해주세요.")
    raw = await attachment.read()
    rofl.validate_rofl_input_size(raw)
    replay_full_version, replay_patch = extract_rofl_client_version(raw)
    current_full_version, current_patch = await get_current_lol_patch_version()
    if replay_patch != current_patch:
        raise ValueError(
            f"현재 패치의 리플레이만 신청할 수 있습니다. "
            f"리플레이 패치: {replay_patch} / 현재 패치: {current_patch}"
        )
    # 버전만 맞고 실제 피드백에 필요한 경기 메타데이터가 깨진 파일도 차단합니다.
    rows = await asyncio.to_thread(rofl.read_rofl_player_stats_from_bytes, raw)
    if not rows:
        raise ValueError("ROFL에서 경기 데이터를 읽지 못했습니다.")
    return {
        "replay_full_version": replay_full_version,
        "replay_patch": replay_patch,
        "current_full_version": current_full_version,
        "current_patch": current_patch,
        "player_count": len(rows),
    }


FEEDBACK_DM_REPLY_CONTEXT_KEY = "_feedback_dm_reply_contexts"


def _feedback_embed_field(embed, field_name):
    for field in getattr(embed, "fields", []) or []:
        if str(getattr(field, "name", "")) == field_name:
            return str(getattr(field, "value", "") or "")
    return ""


def _feedback_extract_first_snowflake(value):
    match = re.search(r"\d{15,25}", str(value or ""))
    return int(match.group(0)) if match else None


def _feedback_request_context_from_message(message):
    embeds = list(getattr(message, "embeds", []) or [])
    if not embeds:
        return {}
    embed = embeds[0]
    return {
        "user_id": _feedback_extract_first_snowflake(_feedback_embed_field(embed, "요청자")),
        "guild_id": _feedback_extract_first_snowflake(_feedback_embed_field(embed, "서버")),
        "channel_id": _feedback_extract_first_snowflake(_feedback_embed_field(embed, "채널")),
        "riot_id": _feedback_embed_field(embed, "수강생 Riot ID").replace("`", "").strip(),
        "game_type": _feedback_embed_field(embed, "경기 종류").replace("`", "").strip(),
    }


def _feedback_store_reply_context(guild_id, dm_message_id, *, user_id, riot_id="", game_type=""):
    gid = str(guild_id or "")
    if not gid:
        return
    guild_data = bot.user_data.setdefault(gid, {})
    contexts = guild_data.setdefault(FEEDBACK_DM_REPLY_CONTEXT_KEY, {})
    if not isinstance(contexts, dict):
        contexts = {}
        guild_data[FEEDBACK_DM_REPLY_CONTEXT_KEY] = contexts
    contexts[str(dm_message_id)] = {
        "user_id": str(user_id or ""),
        "riot_id": str(riot_id or ""),
        "game_type": str(game_type or ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if len(contexts) > 100:
        ordered = sorted(
            contexts.items(),
            key=lambda item: str((item[1] or {}).get("created_at") or ""),
            reverse=True,
        )
        guild_data[FEEDBACK_DM_REPLY_CONTEXT_KEY] = dict(ordered[:100])
    bot.save_lucid_data(gid)


def _feedback_find_reply_context(dm_message_id):
    key = str(dm_message_id or "")
    if not key:
        return None, None
    for gid, guild_data in bot.user_data.items():
        if not isinstance(guild_data, dict):
            continue
        contexts = guild_data.get(FEEDBACK_DM_REPLY_CONTEXT_KEY) or {}
        if isinstance(contexts, dict) and key in contexts:
            return str(gid), contexts.get(key) or {}
    return None, None


async def _feedback_fetch_user(user_id):
    if not user_id:
        return None
    try:
        return bot.get_user(int(user_id)) or await bot.fetch_user(int(user_id))
    except (ValueError, TypeError, discord.NotFound, discord.HTTPException):
        return None


async def _feedback_deliver_operator_message(interaction, *, kind, body):
    context = _feedback_request_context_from_message(interaction.message)
    target_user = await _feedback_fetch_user(context.get("user_id"))
    if target_user is None:
        return await interaction.response.send_message(
            "⚠️ 피드백 신청자를 찾지 못했습니다.",
            ephemeral=True,
        )

    clean = build_global_announcement_content(body)
    if not clean:
        return await interaction.response.send_message("⚠️ 전송할 내용을 입력해주세요.", ephemeral=True)
    if len(clean) > 1800:
        return await interaction.response.send_message("⚠️ 내용은 1800자 이하로 입력해주세요.", ephemeral=True)

    if kind == "payment":
        title = "💳 피드백 결제 안내"
        intro = "경기 자료 확인이 완료되었습니다."
    elif kind == "reject":
        title = "❌ 피드백 신청 안내"
        intro = "신청하신 피드백을 진행하기 어려워 안내드립니다."
    else:
        title = "💬 코치 메시지"
        intro = "피드백 신청과 관련해 코치가 메시지를 보냈습니다."

    embed = discord.Embed(
        title=title,
        description=f"{intro}\n\n{clean}",
        color=0x5865F2 if kind != "reject" else 0xED4245,
        timestamp=datetime.now(timezone.utc),
    )
    if context.get("riot_id"):
        embed.add_field(name="Riot ID", value=f"`{context['riot_id']}`", inline=True)
    if context.get("game_type"):
        embed.add_field(name="경기 종류", value=f"`{context['game_type']}`", inline=True)
    embed.set_footer(text="문의가 있으면 아래 답장 버튼을 눌러주세요.")

    try:
        dm_message = await target_user.send(
            embed=embed,
            view=FeedbackUserReplyView(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.Forbidden:
        return await interaction.response.send_message(
            "⚠️ 신청자에게 DM을 보낼 수 없습니다. 상대방의 DM 설정을 확인해주세요.",
            ephemeral=True,
        )
    except discord.HTTPException as exc:
        return await interaction.response.send_message(
            f"⚠️ DM 전송에 실패했습니다: `{str(exc)[:300]}`",
            ephemeral=True,
        )

    _feedback_store_reply_context(
        context.get("guild_id"),
        dm_message.id,
        user_id=context.get("user_id"),
        riot_id=context.get("riot_id") or "",
        game_type=context.get("game_type") or "",
    )

    label = {
        "payment": "결제 안내",
        "reject": "신청 거절 안내",
        "dm": "DM",
    }[kind]
    await interaction.response.send_message(
        f"✅ {label}을(를) 신청자에게 전송했습니다.",
        ephemeral=True,
    )


class FeedbackOperatorTextModal(discord.ui.Modal):
    def __init__(self, *, kind):
        titles = {"payment": "결제 안내", "reject": "신청 거절", "dm": "DM 전송"}
        labels = {"payment": "결제 안내 내용", "reject": "거절 사유", "dm": "보낼 메시지"}
        placeholders = {
            "payment": "예: 피드백 금액은 20,000원입니다. 입금 계좌/결제 방법을 함께 적어주세요.",
            "reject": "예: 현재 확인 가능한 경기 자료가 없어 이번 신청은 진행하기 어렵습니다.",
            "dm": "예: 3시간 뒤에 피드백 진행이 가능한데 괜찮으세요?",
        }
        super().__init__(title=titles[kind], timeout=600)
        self.kind = kind
        self.body = discord.ui.TextInput(
            label=labels[kind],
            placeholder=placeholders[kind],
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1800,
        )
        self.add_item(self.body)

    async def on_submit(self, interaction):
        if not is_bot_owner(interaction):
            return await interaction.response.send_message(
                "🚫 봇 오너만 사용할 수 있습니다.",
                ephemeral=True,
            )
        await _feedback_deliver_operator_message(
            interaction,
            kind=self.kind,
            body=str(self.body.value),
        )


class FeedbackOperatorActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction):
        if is_bot_owner(interaction):
            return True
        await interaction.response.send_message("🚫 봇 오너만 사용할 수 있습니다.", ephemeral=True)
        return False

    @discord.ui.button(
        label="결제 안내",
        emoji="💳",
        style=discord.ButtonStyle.success,
        custom_id="lucidgame:feedback:operator:payment",
    )
    async def payment(self, interaction, button):
        await interaction.response.send_modal(FeedbackOperatorTextModal(kind="payment"))

    @discord.ui.button(
        label="신청 거절",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        custom_id="lucidgame:feedback:operator:reject",
    )
    async def reject(self, interaction, button):
        await interaction.response.send_modal(FeedbackOperatorTextModal(kind="reject"))

    @discord.ui.button(
        label="DM 전송",
        emoji="💬",
        style=discord.ButtonStyle.secondary,
        custom_id="lucidgame:feedback:operator:dm",
    )
    async def direct_message(self, interaction, button):
        await interaction.response.send_modal(FeedbackOperatorTextModal(kind="dm"))


async def _feedback_forward_user_reply(interaction, body):
    clean = build_global_announcement_content(body)
    if not clean:
        return await interaction.response.send_message("⚠️ 답장 내용을 입력해주세요.", ephemeral=True)
    if len(clean) > 1800:
        return await interaction.response.send_message("⚠️ 답장은 1800자 이하로 입력해주세요.", ephemeral=True)

    gid, context = _feedback_find_reply_context(getattr(interaction.message, "id", None))
    if not gid:
        return await interaction.response.send_message(
            "⚠️ 이 메시지의 피드백 신청 정보를 찾지 못했습니다.",
            ephemeral=True,
        )

    guild = bot.get_guild(int(gid)) if str(gid).isdigit() else None
    alert_channel = get_feedback_alert_channel(guild, gid) if guild else None
    owner = await get_feedback_owner()

    embed = discord.Embed(
        title="↩️ 피드백 신청자 답장",
        description=clean,
        color=0x57F287,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="요청자", value=format_feedback_user_info(interaction.user), inline=False)
    if context.get("riot_id"):
        embed.add_field(name="수강생 Riot ID", value=f"`{context['riot_id']}`", inline=True)
    if context.get("game_type"):
        embed.add_field(name="경기 종류", value=f"`{context['game_type']}`", inline=True)
    if guild:
        embed.add_field(
            name="서버",
            value=f"{discord.utils.escape_markdown(guild.name)}\n`{guild.id}`",
            inline=True,
        )
    embed.set_footer(text="아래 버튼으로 이어서 응답할 수 있습니다.")

    delivered = []
    if owner:
        try:
            await owner.send(
                embed=embed,
                view=FeedbackOperatorActionView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            delivered.append("owner")
        except (discord.Forbidden, discord.HTTPException):
            pass
    if alert_channel:
        try:
            await alert_channel.send(
                embed=embed,
                view=FeedbackOperatorActionView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            delivered.append("channel")
        except (discord.Forbidden, discord.HTTPException):
            pass

    if not delivered:
        return await interaction.response.send_message(
            "⚠️ 코치에게 답장을 전달하지 못했습니다. 잠시 후 다시 시도해주세요.",
            ephemeral=True,
        )

    await interaction.response.send_message("✅ 코치에게 답장을 전달했습니다.", ephemeral=True)


class FeedbackUserReplyModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="코치에게 답장", timeout=600)
        self.body = discord.ui.TextInput(
            label="답장 내용",
            placeholder="코치에게 전달할 내용을 입력해주세요.",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1800,
        )
        self.add_item(self.body)

    async def on_submit(self, interaction):
        await _feedback_forward_user_reply(interaction, str(self.body.value))


class FeedbackUserReplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="답장",
        emoji="↩️",
        style=discord.ButtonStyle.primary,
        custom_id="lucidgame:feedback:user:reply",
    )
    async def reply(self, interaction, button):
        await interaction.response.send_modal(FeedbackUserReplyModal())


async def submit_feedback_request_payload(
    interaction: discord.Interaction,
    닉네임태그: str,
    챔피언kda: str,
    문의사항: str,
    rofl파일: discord.Attachment = None,
    *,
    경기종류: str = "일반/랭크",
    rofl필수: bool = False,
):
    riot_id = str(닉네임태그 or "").strip().replace("\\n", " ")
    champion_kda = str(챔피언kda or "").strip().replace("\\n", " ")
    body = build_global_announcement_content(문의사항)
    title = f"{riot_id} / {champion_kda}"
    if not riot_id:
        return await interaction.response.send_message("⚠️ 닉네임#태그를 입력해주세요. 예: hide on bush#KR1", ephemeral=True)
    if not champion_kda:
        return await interaction.response.send_message("⚠️ 챔피언 및 K/D/A를 입력해주세요. 예: 아리 7/4/12", ephemeral=True)
    if not body:
        return await interaction.response.send_message("⚠️ 문의사항을 입력해주세요.", ephemeral=True)
    if len(riot_id) > 80:
        return await interaction.response.send_message("⚠️ 닉네임#태그는 80자 이하로 입력해주세요.", ephemeral=True)
    if len(champion_kda) > 120:
        return await interaction.response.send_message("⚠️ 챔피언 및 K/D/A는 120자 이하로 입력해주세요.", ephemeral=True)
    if len(body) > 1800:
        return await interaction.response.send_message("⚠️ 문의사항은 1800자 이하로 입력해주세요.", ephemeral=True)
    if rofl필수 and rofl파일 is None:
        return await interaction.response.send_message(
            "⚠️ 사용자 설정 게임은 `.rofl` 리플레이 파일이 반드시 필요합니다.",
            ephemeral=True,
        )
    filename = rofl파일.filename if rofl파일 else None
    if filename and not filename.lower().endswith(".rofl"):
        return await interaction.response.send_message("⚠️ `.rofl` 리플레이 파일만 업로드해주세요.", ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)

    rofl_info = None
    if rofl파일:
        try:
            rofl_info = await validate_feedback_rofl_current_patch(rofl파일)
        except Exception as exc:
            logger.info(
                "피드백 ROFL 검증 거절: guild_id=%s user_id=%s file=%s reason=%s",
                interaction.guild_id,
                getattr(interaction.user, "id", None),
                filename,
                exc,
            )
            return await interaction.followup.send(f"⚠️ {str(exc)[:700]}", ephemeral=True)

    owner = await get_feedback_owner()
    guild = interaction.guild
    channel = interaction.channel
    alert_channel = get_feedback_alert_channel(guild, str(interaction.guild_id)) if interaction.guild_id else None
    if not owner and not alert_channel:
        return await interaction.followup.send("⚠️ 피드백 요청을 받을 봇 오너 또는 알림 채널을 찾지 못했습니다.", ephemeral=True)

    embed = discord.Embed(
        title=f"📩 피드백 요청 - {title[:220]}",
        description=body[:4096],
        color=0x4f8cff,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="요청자", value=format_feedback_user_info(interaction.user), inline=False)
    embed.add_field(name="경기 종류", value=f"`{경기종류}`", inline=True)
    embed.add_field(name="수강생 Riot ID", value=f"`{riot_id}`", inline=True)
    embed.add_field(name="챔피언 및 K/D/A", value=f"`{champion_kda}`", inline=True)
    embed.add_field(
        name="서버",
        value=f"{discord.utils.escape_markdown(getattr(guild, 'name', 'DM/알 수 없음'))}\n`{getattr(guild, 'id', 'unknown')}`",
        inline=True,
    )
    embed.add_field(
        name="채널",
        value=f"{getattr(channel, 'mention', '알 수 없음')}\n`{getattr(channel, 'id', 'unknown')}`",
        inline=True,
    )
    if rofl파일:
        size_mb = (getattr(rofl파일, "size", 0) or 0) / (1024 * 1024)
        attachment_value = (
            f"`{filename}` ({size_mb:.1f}MB)\n"
            f"[다운로드 링크]({rofl파일.url})"
        )
        if rofl_info:
            attachment_value += (
                f"\n패치: **{rofl_info['replay_patch']}** · "
                f"현재 패치 확인 완료 · 참가자 데이터 {rofl_info['player_count']}명"
            )
    else:
        attachment_value = "없음 - 일반/랭크 경기 전적 확인 필요"
    embed.add_field(name="첨부 파일", value=attachment_value, inline=False)
    embed.add_field(
        name="진행 상태",
        value="경기 확인 후 결제 안내 → 결제 완료 후 피드백 진행",
        inline=False,
    )
    embed.set_footer(text="아래 버튼으로 결제 안내, 신청 거절, DM 전송을 할 수 있습니다.")

    delivered_to = []
    delivery_errors = []
    if owner:
        try:
            await owner.send(
                embed=embed,
                view=FeedbackOperatorActionView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            delivered_to.append("봇 오너 DM")
        except discord.Forbidden:
            delivery_errors.append("봇 오너 DM이 닫혀 있음")
        except discord.HTTPException as exc:
            delivery_errors.append(f"봇 오너 DM 실패: {str(exc)[:160]}")

    if alert_channel:
        try:
            await alert_channel.send(
                embed=embed,
                view=FeedbackOperatorActionView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            delivered_to.append(f"알림 채널 #{alert_channel.name}")
        except discord.Forbidden:
            delivery_errors.append(f"알림 채널 권한 부족: #{alert_channel.name}")
        except discord.HTTPException as exc:
            delivery_errors.append(f"알림 채널 실패: {str(exc)[:160]}")

    if not delivered_to:
        error_text = " / ".join(delivery_errors) if delivery_errors else "알 수 없는 전송 실패"
        return await interaction.followup.send(f"⚠️ 피드백 요청 전송에 실패했습니다: `{error_text[:500]}`", ephemeral=True)

    notice = ""
    if delivery_errors:
        notice = "\n일부 알림 전송 실패: " + " / ".join(delivery_errors)[:500]
    await interaction.followup.send(
        "✅ 피드백 신청이 접수되었습니다.\n"
        "경기 자료 확인 후 결제 안내가 전달되며, 결제 완료 후 피드백이 진행됩니다.\n"
        f"완료된 피드백은 DM으로 전달됩니다.\n전송 위치: {', '.join(delivered_to)}{notice}",
        ephemeral=True,
    )
    try:
        await save_feedback_reservation_to_coach_db(interaction, riot_id, champion_kda, body, rofl파일)
    except Exception:
        logger.exception("Discord feedback DB save failed")


@bot.tree.command(name="피드백", description="코치진에게 리플레이 파일과 비대면 피드백 요청을 보냅니다.")
@app_commands.describe(
    경기종류="일반/랭크 또는 사용자 설정 게임을 선택해주세요.",
    닉네임태그="수강생 Riot ID를 적어주세요. 예: hide on bush#KR1",
    챔피언kda="챔피언과 K/D/A를 적어주세요. 예: 아리 7/4/12",
    문의사항="피드백 받고 싶은 내용을 적어주세요. 예: 라인전, 한타 포지션, 운영",
    rofl파일="사용자 설정은 필수. 현재 패치의 .rofl 파일만 신청할 수 있습니다.",
)
@app_commands.choices(경기종류=[
    app_commands.Choice(name="일반/랭크", value="normal"),
    app_commands.Choice(name="사용자 설정", value="custom"),
])
async def request_feedback(
    interaction: discord.Interaction,
    경기종류: app_commands.Choice[str],
    닉네임태그: str,
    챔피언kda: str,
    문의사항: str,
    rofl파일: discord.Attachment = None,
):
    is_custom = 경기종류.value == "custom"
    return await submit_feedback_request_payload(
        interaction,
        닉네임태그,
        챔피언kda,
        문의사항,
        rofl파일,
        경기종류="사용자 설정" if is_custom else "일반/랭크",
        rofl필수=is_custom,
    )


@bot.tree.command(name="피드백전송", description="[봇 오너] 피드백 요청자에게 비대면 피드백 DM을 보냅니다.")
@app_commands.describe(
    유저id="피드백을 받을 유저의 Discord 고유 ID",
    내용="전송할 피드백 내용. 줄바꿈은 \\n 으로 입력",
    첨부파일1="피드백 첨부파일",
    첨부파일2="피드백 첨부파일",
    첨부파일3="피드백 첨부파일",
    첨부파일4="피드백 첨부파일",
)
async def send_feedback_reply(
    interaction: discord.Interaction,
    유저id: str,
    내용: str,
    첨부파일1: discord.Attachment = None,
    첨부파일2: discord.Attachment = None,
    첨부파일3: discord.Attachment = None,
    첨부파일4: discord.Attachment = None,
):
    if not is_bot_owner(interaction):
        return await interaction.response.send_message("🚫 봇 오너만 사용할 수 있습니다.", ephemeral=True)
    if not acquire_dm_command_lock(interaction.id):
        return

    uid = "".join(ch for ch in str(유저id or "") if ch.isdigit())
    if not uid:
        return await interaction.response.send_message("⚠️ 피드백을 받을 유저의 Discord 고유 ID를 입력해주세요.", ephemeral=True)

    text = build_global_announcement_content(내용)
    if not text:
        return await interaction.response.send_message("⚠️ 전송할 피드백 내용을 입력해주세요.", ephemeral=True)
    if len(text) > 1900:
        return await interaction.response.send_message("⚠️ 피드백 내용은 1900자 이하로 입력해주세요.", ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        target_user = bot.get_user(int(uid)) or await bot.fetch_user(int(uid))
    except (ValueError, discord.NotFound):
        return await interaction.followup.send("⚠️ 해당 Discord ID의 유저를 찾지 못했습니다.", ephemeral=True)
    except discord.HTTPException as exc:
        return await interaction.followup.send(f"⚠️ 유저 조회에 실패했습니다: `{str(exc)[:300]}`", ephemeral=True)

    try:
        file_payloads = await read_broadcast_attachments([첨부파일1, 첨부파일2, 첨부파일3, 첨부파일4])
    except RuntimeError as e:
        return await interaction.followup.send(f"⚠️ {e}", ephemeral=True)

    content = f"📬 **루시드 피드백 답변이 도착했습니다.**\n\n{text}"
    try:
        await target_user.send(
            content=content,
            files=clone_broadcast_files(file_payloads),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.Forbidden:
        return await interaction.followup.send("⚠️ 해당 유저에게 DM을 보낼 수 없습니다. 서버 멤버 DM 허용 설정을 확인해주세요.", ephemeral=True)
    except discord.HTTPException as exc:
        return await interaction.followup.send(f"⚠️ 피드백 DM 전송에 실패했습니다: `{str(exc)[:300]}`", ephemeral=True)

    await interaction.followup.send(f"✅ {target_user.mention}님에게 피드백 DM을 전송했습니다. (`{target_user.id}`)", ephemeral=True)

async def send_channel_message(
    interaction: discord.Interaction,
    내용: str,
    첨부파일1: discord.Attachment = None,
    첨부파일2: discord.Attachment = None,
    첨부파일3: discord.Attachment = None,
    첨부파일4: discord.Attachment = None,
    첨부파일5: discord.Attachment = None,
    첨부파일6: discord.Attachment = None,
    첨부파일7: discord.Attachment = None,
    첨부파일8: discord.Attachment = None,
):
    if not is_bot_owner(interaction):
        return await interaction.response.send_message("🚫 봇 오너만 사용할 수 있습니다.", ephemeral=True)
    if not acquire_dm_command_lock(interaction.id):
        return

    channel = interaction.channel
    if not channel or not hasattr(channel, "send"):
        return await interaction.response.send_message("⚠️ 현재 채널에 메시지를 보낼 수 없습니다.", ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)
    attachments = [
        첨부파일1, 첨부파일2, 첨부파일3, 첨부파일4,
        첨부파일5, 첨부파일6, 첨부파일7, 첨부파일8,
    ]
    try:
        file_payloads = await read_broadcast_attachments(attachments)
    except RuntimeError as e:
        return await interaction.followup.send(f"⚠️ {e}", ephemeral=True)

    content = build_global_announcement_content(내용)
    if content and len(content) > 2000:
        return await interaction.followup.send("⚠️ 일반메세지 내용은 2000자 이하로 입력해주세요.", ephemeral=True)
    if not content and not file_payloads:
        return await interaction.followup.send("⚠️ 내용 또는 첨부파일 중 하나 이상은 입력해주세요.", ephemeral=True)

    try:
        await channel.send(
            content=content,
            files=clone_broadcast_files(file_payloads),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        return await interaction.followup.send(f"⚠️ 채널 메시지 전송에 실패했습니다: `{str(exc)[:300]}`", ephemeral=True)

    await interaction.followup.send("✅ 현재 채널에 일반메세지를 전송했습니다.", ephemeral=True)












@bot.tree.command(name="조치", description=".")
@app_commands.default_permissions(manage_guild=True)
async def owner_team_separation(
    interaction: discord.Interaction,
    유저1: discord.Member,
    유저2: discord.Member
):
    if not is_match_admin(interaction):
        return await interaction.response.send_message("사용할 수 없습니다.", ephemeral=True)
    if 유저1.id == 유저2.id:
        return await interaction.response.send_message("⚠️ 서로 다른 유저를 선택해주세요.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    gid = str(interaction.guild_id)
    pairs = get_team_separation_pairs(gid)
    target_pair = normalize_team_separation_pair(유저1.id, 유저2.id)
    if target_pair in pairs:
        pairs.remove(target_pair)
        action_text = "해제"
    else:
        pairs.append(target_pair)
        action_text = "적용"
    bot.user_data.setdefault(gid, {})[TEAM_SEPARATION_KEY] = pairs
    bot.save_lucid_data(gid)

    await interaction.followup.send(
        f"✅ {유저1.mention} · {유저2.mention} 같은 팀 방지 조치를 **{action_text}**했습니다.",
        ephemeral=True
    )

# `/봇재시작` 독립 명령어로 사용.





















































































# ==============================================================================
# [2. 대기열(큐) 매칭 제어 시스템]
# ==============================================================================






# ==============================================================================
# [UX 2026-08-18] 통합 명령어 / MVP 포인트
# ==============================================================================






placement_action_choices=[
    app_commands.Choice(name="평가",value="evaluate"),
    app_commands.Choice(name="초기화",value="reset"),
    app_commands.Choice(name="전체초기화",value="reset_all"),
]

@bot.tree.command(name="배치관리", description="[관리자] 유저의 티어 배치 관리 패널을 엽니다.")
@app_commands.choices(작업=placement_action_choices, 라인=[app_commands.Choice(name=r,value=r) for r in ROLES]+[app_commands.Choice(name="노밴",value="노밴")], 알림=completion_dm_choices)
async def placement_manage(interaction: discord.Interaction, 작업: app_commands.Choice[str]=None, 유저: discord.Member=None, 라인: app_commands.Choice[str]=None, 티어: str="", 알림: app_commands.Choice[str]=None, 확인: str=""):
    if 작업 is None:
        if 유저 is not None:
            return await open_tier_target_actions(interaction, 유저)
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 내전 관리자만 사용할 수 있습니다.", ephemeral=True)
        return await interaction.response.send_modal(TierAdminTargetSelectModal(interaction.user.id))
    if 작업.value == "evaluate":
        if 유저 is None or 라인 is None or not 티어.strip():
            return await interaction.response.send_message("⚠️ 평가에는 유저, 라인, 티어를 모두 입력해주세요.", ephemeral=True)
        return await evaluate_user(interaction, 유저, 라인, 티어, 알림)
    if 작업.value == "reset":
        if 유저 is None:
            return await interaction.response.send_message("⚠️ 초기화할 유저를 선택해주세요.", ephemeral=True)
        reset_line = 라인 if 라인 and 라인.value in ROLES else None
        return await reset_user(interaction, 유저, reset_line)
    if 작업.value == "reset_all":
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("🚫 디스코드 서버 관리자만 전체초기화를 할 수 있습니다.", ephemeral=True)
        if 확인.strip() != "전체초기화":
            return await interaction.response.send_message("⚠️ 전체 MMR을 초기화하려면 확인 칸에 `전체초기화`를 입력해주세요.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        gid=str(interaction.guild_id)
        count=0
        for uid,data in iter_user_records(bot.user_data.get(gid,{})):
            info=ensure_user_format(data)
            info['mmr']={r:0 for r in ROLES}
            info['eval_scores']={r:[] for r in ROLES}
            info['noban_mmr']=0
            info['streak']=0
            for role in ROLES:
                info['role_stats'][role]['streak'] = 0
            count+=1
        bot.save_lucid_data(gid)
        return await interaction.followup.send(f"🧹 전체 배치/MMR 초기화 완료: **{count}명** · 통산 승패/경기 기록은 유지했습니다.",ephemeral=True)

# ------------------------------------------------------------------------------
# 소환사 관리 UX
# /소환사등록은 최초 등록 전용으로 유지하고, 등록 이후 작업은 이 그룹으로 통합한다.
# ------------------------------------------------------------------------------









































# ==============================================================================
# [5. 가이드북 가이드 명령어 아카이브]
# ==============================================================================

globals().update(matches.register_match_commands(globals()))
globals().update(profiles.register_profiles(globals()))
globals().update(replays.register_replay_commands(globals()))
globals().update(participation.register_participation_commands(globals()))
globals().update(server_admin.register_commands(globals()))
matches.configure(globals())
profiles.configure(globals())

guides.register_commands(
    bot=bot,
    is_feature_enabled=is_feature_enabled,
    get_disabled_feature_message=get_disabled_feature_message,
    league_help=league_help,
    is_match_admin=is_match_admin,
    add_chunked_embed_fields=add_chunked_embed_fields,
    LEAGUE_MODE_NAME=LEAGUE_MODE_NAME,
    LEAGUE_SIM_LABEL=LEAGUE_SIM_LABEL,
    LOW_TIER_MMR_LIMIT=LOW_TIER_MMR_LIMIT,
    MATCH_ADMIN_ROLE_KEY=MATCH_ADMIN_ROLE_KEY,
)

from system_smoke import register_game_system_test

register_game_system_test(bot)

# 봇 실행 모듈
if __name__ == "__main__":
    bot.run(TOKEN)
