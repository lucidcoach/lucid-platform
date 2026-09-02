"""Matchmaking, result processing, MMR mutations, history snapshots, and undo."""

import inspect
import re
import uuid

import discord
from discord import app_commands
import lol_core as shared_lol
from lol_lineup_engine import (
    LineupConfig,
    LineupNotFoundError,
    LineupPlayerInput,
    find_classic_lineup,
    get_lineup_preference_score,
    select_diverse_permutations,
)


TEAM_VOICE_CHANNEL_SETTLE_SECONDS = 0.75
TEAM_VOICE_MOVE_INTERVAL_SECONDS = 0.20
TEAM_VOICE_MOVE_VERIFY_SECONDS = 0.50


def _active_game_id(gid, queue_key):
    timestamp = now_kst().strftime("%Y%m%d%H%M%S") if "now_kst" in globals() else "game"
    return f"{timestamp}-{queue_key}-{uuid.uuid4().hex[:8]}"


def initialize_active_game_state(gid, queue_key, state):
    """Add durable identity metadata without changing the match payload."""
    state.setdefault("guild_id", str(gid))
    state.setdefault("queue_key", str(queue_key))
    state.setdefault("game_id", _active_game_id(gid, queue_key))
    state.setdefault("status", "active")
    state.setdefault(
        "created_at",
        now_kst().strftime("%Y-%m-%d %H:%M:%S") if "now_kst" in globals() else "",
    )
    state.setdefault("voice_channels", {})
    return state


def _voice_state_key(channel_name, index):
    text = str(channel_name or "")
    lowered = text.lower()
    if "블루" in text or "blue" in lowered:
        return "blue"
    if "레드" in text or "red" in lowered:
        return "red"
    team_match = re.search(r"(\d+)팀", text)
    if team_match:
        return f"team_{team_match.group(1)}"
    return str(index + 1)


def _persist_active_game(gid, state):
    if not isinstance(state, dict):
        return
    try:
        bot.save_lucid_data(gid)
    except Exception:
        logger.exception("진행 게임 스냅샷 저장 실패: guild=%s game_id=%s", gid, state.get("game_id"))


def configure(runtime):
    globals().update(runtime)


def register_match_commands(runtime):
    """Register match commands and return callbacks used by the main bot."""
    globals().update(runtime)

    def _sync_runtime():
        globals().update(runtime)

    def get_team_strength_adjustment(avg_gap):
        return shared_lol.get_team_strength_adjustment(avg_gap, TEAM_MMR_ADJUSTMENT_CAP)
    
    
    def get_player_team_delta_adjustment(player_team, is_win, blue_avg, red_avg):
        return shared_lol.get_player_team_delta_adjustment(
            player_team,
            is_win,
            blue_avg,
            red_avg,
            TEAM_MMR_ADJUSTMENT_CAP,
        )


    def append_match_history(gid, record):
        guild_data = bot.user_data.setdefault(gid, {})
        history = guild_data.setdefault(MATCH_HISTORY_KEY, [])
        record_id = str(record.get("id") or "") if isinstance(record, dict) else ""
        if record_id and any(str(item.get("id") or "") == record_id for item in history if isinstance(item, dict)):
            logger.warning("중복 경기 기록 건너뜀: guild_id=%s match_id=%s", gid, record_id)
            return False
        history.append(record)
        if MAX_MATCH_HISTORY > 0 and len(history) > MAX_MATCH_HISTORY:
            del history[:-MAX_MATCH_HISTORY]
        maybe_schedule_patch_summary_promo(gid)
        return True


    def has_match_history_id(gid, match_id):
        match_id = str(match_id or "")
        if not match_id:
            return False
        return any(
            isinstance(item, dict) and str(item.get("id") or "") == match_id
            for item in bot.user_data.get(gid, {}).get(MATCH_HISTORY_KEY, [])
        )


    def mark_match_result_processing(gid, game_state, winner):
        if game_state.get("status") == "result_processing":
            return False
        game_state["status"] = "result_processing"
        game_state["pending_winner"] = str(winner)
        if bot.save_lucid_data(gid) is False:
            game_state["status"] = "active"
            game_state.pop("pending_winner", None)
            raise RuntimeError("경기 결과 핵심 저장에 실패했습니다.")
        return True


    def mark_match_history_cancelled(gid, match_id):
        if not match_id:
            return
    
        history = bot.user_data.get(gid, {}).get(MATCH_HISTORY_KEY, [])
        for record in reversed(history):
            if record.get("id") == match_id:
                record["cancelled"] = True
                record["cancelled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return


    def is_match_enabled(gid):
        return bot.user_data.setdefault(gid, {}).get(MATCH_ENABLED_KEY, True)
    
    def set_match_enabled(gid, enabled):
        bot.user_data.setdefault(gid, {})[MATCH_ENABLED_KEY] = bool(enabled)
        bot.save_lucid_data(gid)
    
    def get_start_wait_queues(gid):
        guild_data = bot.user_data.setdefault(gid, {})
        raw = guild_data.setdefault(MATCH_START_WAIT_KEY, [])
        if not isinstance(raw, list):
            raw = []
            guild_data[MATCH_START_WAIT_KEY] = raw
        return {str(item) for item in raw}
    
    def is_start_wait_enabled(gid, queue_key):
        return str(queue_key) in get_start_wait_queues(gid)
    
    def set_start_wait_enabled(gid, queue_key, enabled=True):
        guild_data = bot.user_data.setdefault(gid, {})
        waits = get_start_wait_queues(gid)
        if enabled:
            waits.add(str(queue_key))
        else:
            waits.discard(str(queue_key))
        guild_data[MATCH_START_WAIT_KEY] = sorted(waits)
        bot.save_lucid_data(gid)
    
    def get_reset_start_wait_queues(gid):
        guild_data = bot.user_data.setdefault(gid, {})
        raw = guild_data.setdefault(RESET_START_WAIT_KEY, [])
        if not isinstance(raw, list):
            raw = []
            guild_data[RESET_START_WAIT_KEY] = raw
        return {str(item) for item in raw}
    
    def set_reset_start_wait_enabled(gid, queue_key, enabled=True):
        guild_data = bot.user_data.setdefault(gid, {})
        waits = get_reset_start_wait_queues(gid)
        if enabled:
            waits.add(str(queue_key))
        else:
            waits.discard(str(queue_key))
        guild_data[RESET_START_WAIT_KEY] = sorted(waits)
        bot.save_lucid_data(gid)
    
    def clear_reset_start_wait_after_match(gid, queue_key):
        if str(queue_key) not in get_reset_start_wait_queues(gid):
            return False
        set_reset_start_wait_enabled(gid, queue_key, False)
        set_start_wait_enabled(gid, queue_key, False)
        return True
    
    def get_match_blocked_role_id(gid):
        return bot.user_data.setdefault(gid, {}).get(MATCH_BLOCKED_ROLE_KEY)
    
    def set_match_blocked_role(gid, role_id):
        bot.user_data.setdefault(gid, {})[MATCH_BLOCKED_ROLE_KEY] = int(role_id)
        bot.save_lucid_data(gid)
    
    def clear_match_blocked_role(gid):
        guild_data = bot.user_data.setdefault(gid, {})
        if MATCH_BLOCKED_ROLE_KEY not in guild_data:
            return False
        guild_data.pop(MATCH_BLOCKED_ROLE_KEY, None)
        bot.save_lucid_data(gid)
        return True
    
    def get_member_blocked_match_role(gid, member):
        role_id = get_match_blocked_role_id(gid)
        if not role_id or not getattr(member, "roles", None):
            return None
        return discord.utils.get(member.roles, id=int(role_id))
    
    def get_match_frequency_key(gid):
        key = bot.user_data.setdefault(gid, {}).get(MATCH_FREQUENCY_KEY, DEFAULT_MATCH_FREQUENCY)
        return key if key in MATCH_FREQUENCY_PRESETS else DEFAULT_MATCH_FREQUENCY
    
    def get_match_frequency_config(gid):
        return MATCH_FREQUENCY_PRESETS[get_match_frequency_key(gid)]
    
    
    def get_provisional_mmr_config(gid):
        return PROVISIONAL_MMR_PRESETS.get(
            get_match_frequency_key(gid),
            PROVISIONAL_MMR_PRESETS[DEFAULT_MATCH_FREQUENCY],
        )
    
    
    def _normalize_provisional_role(role):
        role = str(role or "").strip()
        if not role or role == PROVISIONAL_ALL_ROLES_VALUE:
            return None
        return role if role in ROLES else None
    
    
    def _sync_provisional_summary(state):
        role_states = state.get("role_states") if isinstance(state.get("role_states"), dict) else {}
        active_roles = [
            role for role in ROLES
            if isinstance(role_states.get(role), dict) and bool(role_states[role].get("active"))
        ]
        state["active"] = bool(active_roles)
        state["active_roles"] = active_roles
        # Legacy readers may still inspect top-level games. Keep a harmless summary.
        state["games"] = max(
            [int((role_states.get(role) or {}).get("games", 0) or 0) for role in active_roles] or [0]
        )
        return state
    
    
    def get_provisional_mmr_state(user_info):
        state = user_info.get(PROVISIONAL_MMR_KEY)
        if not isinstance(state, dict):
            state = {}
            user_info[PROVISIONAL_MMR_KEY] = state
    
        role_states = state.get("role_states")
        if not isinstance(role_states, dict):
            # Backward compatibility: an old global provisional state becomes an
            # all-role state while preserving its existing progress on every role.
            legacy_active = bool(state.get("active", False))
            legacy_games = int(state.get("games", 0) or 0)
            role_states = {}
            if legacy_active:
                for role in ROLES:
                    role_state = {"active": True, "games": legacy_games}
                    for key in ("started_at", "started_by", "completed_at"):
                        if state.get(key) is not None:
                            role_state[key] = state.get(key)
                    role_states[role] = role_state
            state["role_states"] = role_states
    
        for role in ROLES:
            role_state = role_states.get(role)
            if role_state is not None and not isinstance(role_state, dict):
                role_states.pop(role, None)
                continue
            if isinstance(role_state, dict):
                role_state.setdefault("active", False)
                role_state.setdefault("games", 0)
    
        return _sync_provisional_summary(state)
    
    
    def get_provisional_role_state(user_info, role, *, create=False):
        state = get_provisional_mmr_state(user_info)
        normalized = _normalize_provisional_role(role)
        if normalized is None:
            return None
        role_states = state.setdefault("role_states", {})
        role_state = role_states.get(normalized)
        if not isinstance(role_state, dict):
            if not create:
                return None
            role_state = {"active": False, "games": 0}
            role_states[normalized] = role_state
        role_state.setdefault("active", False)
        role_state.setdefault("games", 0)
        return role_state
    
    
    def is_provisional_mmr_active(user_info, role=None):
        state = get_provisional_mmr_state(user_info)
        normalized = _normalize_provisional_role(role)
        if normalized is None:
            return bool(state.get("active"))
        role_state = get_provisional_role_state(user_info, normalized, create=False)
        return bool(role_state and role_state.get("active"))
    
    
    def set_provisional_mmr_state(user_info, *, active, actor_id=None, reset_games=False, role=None):
        state = get_provisional_mmr_state(user_info)
        normalized = _normalize_provisional_role(role)
        target_roles = [normalized] if normalized else list(ROLES)
        now_text = now_kst().strftime("%Y-%m-%d %H:%M:%S")
    
        for target_role in target_roles:
            role_state = get_provisional_role_state(user_info, target_role, create=True)
            role_state["active"] = bool(active)
            if reset_games:
                role_state["games"] = 0
            if active:
                role_state["started_at"] = now_text
                if actor_id is not None:
                    role_state["started_by"] = str(actor_id)
                role_state.pop("completed_at", None)
            else:
                role_state["completed_at"] = now_text
    
        return _sync_provisional_summary(state)
    
    
    def get_provisional_mmr_status_text(gid, user_info):
        state = get_provisional_mmr_state(user_info)
        config = get_provisional_mmr_config(gid)
        target = int(config["games"])
        active_roles = [role for role in ROLES if is_provisional_mmr_active(user_info, role)]
        if not active_roles:
            return "정식 배치"
    
        role_states = state.get("role_states", {})
        progress = []
        for role in active_roles:
            games = int((role_states.get(role) or {}).get("games", 0) or 0)
            progress.append(f"{role} {min(games, target)}/{target}")
        role_label = "전체 라인" if len(active_roles) == len(ROLES) else ", ".join(active_roles)
        return (
            f"🟡 임시 배치 · {role_label} · "
            f"{' / '.join(progress)} · 기본 변동 ±{config['delta']}점"
        )
    
    
    def apply_provisional_base_delta(gid, user_info, base_delta, delta_phase, *, role=None, is_low_tier=False, retroactive=False):
        if is_low_tier or retroactive or not is_provisional_mmr_active(user_info, role):
            return base_delta, delta_phase, False
        config = get_provisional_mmr_config(gid)
        return int(config["delta"]), "임시배치", True
    
    
    def advance_provisional_mmr(gid, user_info, role):
        normalized = _normalize_provisional_role(role)
        role_state = get_provisional_role_state(user_info, normalized, create=False) if normalized else None
        if not role_state or not role_state.get("active"):
            return False, False, 0, 0
        config = get_provisional_mmr_config(gid)
        target = int(config["games"])
        role_state["games"] = int(role_state.get("games", 0) or 0) + 1
        completed = role_state["games"] >= target
        if completed:
            role_state["active"] = False
            role_state["completed_at"] = now_kst().strftime("%Y-%m-%d %H:%M:%S")
        _sync_provisional_summary(get_provisional_mmr_state(user_info))
        return True, completed, int(role_state["games"]), target
    
    
    def get_provisional_ai_performance_adjustment(display_score):
        """Visible AI Score -> signed provisional MMR adjustment."""
        score = float(display_score or 0.0)
        if score < 30:
            return -45
        if score < 40:
            return -30
        if score <= 50:
            return 0
        if score <= 70:
            return 15
        if score < 80:
            return 22
        if score <= 100:
            return 35
        if score < 120:
            return 45
        return 55
    
    
    def get_provisional_opponent_adjustment(before_mmr, opponent_mmr):
        """Reward performance against a stronger lane opponent and discount weaker opposition."""
        before = int(before_mmr or 0)
        opponent = int(opponent_mmr or 0)
        if before <= 0 or opponent <= 0:
            return 0
        gap = opponent - before
        # ±600 gap reaches the cap. Positive means the opponent was stronger.
        return max(-30, min(30, int(round(gap / 20.0))))
    
    
    def clamp_provisional_final_delta(original_signed_delta, extra_adjustment):
        """Apply provisional extras without allowing one game to reverse win/loss direction."""
        original = int(original_signed_delta or 0)
        extra = int(extra_adjustment or 0)
        combined = max(
            -PROVISIONAL_AI_TOTAL_DELTA_CAP,
            min(PROVISIONAL_AI_TOTAL_DELTA_CAP, original + extra),
        )
        if original > 0:
            return max(PROVISIONAL_AI_MIN_DIRECTIONAL_DELTA, combined)
        if original < 0:
            return min(-PROVISIONAL_AI_MIN_LOSS_DELTA, combined)
        return combined
    
    def set_match_frequency(gid, frequency_key):
        if frequency_key not in MATCH_FREQUENCY_PRESETS:
            return False
        bot.user_data.setdefault(gid, {})[MATCH_FREQUENCY_KEY] = frequency_key
        bot.save_lucid_data(gid)
        return True
    
    def build_match_frequency_status_text(gid, title="⚙️ **현재 내전 빈도 설정**"):
        key = get_match_frequency_key(gid)
        config = get_match_frequency_config(gid)
        week_count = count_recent_match_history(gid, 7)
        month_count = count_recent_match_history(gid, 30)
        return (
            f"{title}\n"
            f"설정: **{key}** ({config['label']})\n"
            f"배치 기준: 라인별 **{config['placement_games']}판 미만**\n"
            f"배치 구간: `±{config['placement_delta']}점`\n"
            f"정규 구간: `±{config['regular_delta']}점`\n"
            f"최근 7일 내전: **{week_count}회**\n"
            f"최근 30일 내전: **{month_count}회**\n"
            "칭호 조건: 판수/승수형 칭호가 이 빈도 기준으로 자동 조정됩니다.\n"
            "연승/연패 보너스는 기존처럼 기본 변동값에 추가 적용됩니다."
        )
    
    def get_role_match_delta_config(gid, current_plays):
        config = get_match_frequency_config(gid)
        if current_plays < config["placement_games"]:
            return config["placement_delta"], "배치"
        return config["regular_delta"], "정규"
    
    def get_low_tier_match_delta_config(gid, current_plays):
        config = get_match_frequency_config(gid)
        low_tier_config = LOW_TIER_DELTA_PRESETS.get(get_match_frequency_key(gid), LOW_TIER_DELTA_PRESETS[DEFAULT_MATCH_FREQUENCY])
        if current_plays < config["placement_games"]:
            return low_tier_config["placement_delta"], "저티어 배치"
        return low_tier_config["regular_delta"], "저티어 정규"


    def apply_ai_mmr_adjustments_for_record(gid, record):
        """AI Score를 경기 내 순위와 MMR 기대 대비 퍼포먼스를 함께 봐서 미세 보정한다.
    
        매우 뛰어남 +4 / 뛰어남 +2 / 평균 0 / 부진 -1 / 매우 부진 -2.
        공개 결과에는 AI 보정 사유를 따로 표시하지 않는다. 상세 데이터가 늦게 들어와
        같은 라인의 다음 경기를 이미 치른 유저는 과거 레이팅 체인을 보호하기 위해 건너뛴다.
        """
        _sync_runtime()
        if not isinstance(record, dict) or record.get(AI_MMR_APPLIED_KEY):
            return []
        if record.get("mode") != "classic":
            record[AI_MMR_APPLIED_KEY] = True
            return []
    
        match_id = str(record.get("id") or "")
        guild_data = bot.user_data.setdefault(str(gid), {})
        entries = match_stats.get_store(guild_data).get(match_id, {}) or {}
        if len(entries) < 10:
            return []
    
        awards = match_stats.score_match_awards(guild_data, match_id)
        rows = list(awards.get("scores", []) or [])
        if len(rows) < 10:
            return []
        rows.sort(key=lambda row: float(row.get("expectation_score", row.get("score", 0)) or 0), reverse=True)
        values = sorted(float(row.get("expectation_score", row.get("score", 0)) or 0) for row in rows)
        median = (values[4] + values[5]) / 2.0
    
        adjustments = {}
        total = len(rows)
        for rank, row in enumerate(rows, 1):
            uid = str(row.get("user_id") or "")
            score = float(row.get("expectation_score", row.get("score", 0)) or 0)
            residual = float(row.get("relative_adjustment", 0) or 0)
            gap = score - median
            adjustment = 0
    
            # 매우 뛰어난 경기: 경기 최상위권이면서 중앙값을 크게 넘거나 120+ 초특출 경기.
            if rank <= 2 and ((score >= 120.0 and gap >= 12.0) or (gap >= 20.0 and residual >= 0.5)):
                adjustment = 4
            # 뛰어난 경기: 상위 30% + 중앙값 대비 확실한 우위 + 기대치 대비 크게 밀리지 않음.
            elif rank <= 3 and gap >= 10.0 and score >= 90.0 and residual >= -0.5:
                adjustment = 2
            # 매우 부진: 최하위권이면서 중앙값과 큰 차이, 기대치 대비도 부진.
            elif rank >= total - 1 and ((score <= 40.0 and gap <= -12.0) or (gap <= -20.0 and residual <= -0.5)):
                adjustment = -2
            # 부진: 하위 30% + 중앙값 대비 뚜렷한 열세.
            elif rank >= total - 2 and gap <= -10.0 and score <= 75.0 and residual <= 0.5:
                adjustment = -1
    
            if uid:
                adjustments[uid] = adjustment
    
        score_by_uid = {str(row.get("user_id") or ""): row for row in rows}
        player_by_team_role = {
            (str(player.get("team") or ""), str(player.get("role") or "")): player
            for player in (record.get("players", []) or [])
        }
    
        applied_any = False
        for player in record.get("players", []) or []:
            uid = str(player.get("user_id"))
            role = player.get("role")
            user_info = guild_data.get(uid)
            if not isinstance(user_info, dict) or role not in ROLES:
                continue
            user_info = ensure_user_format(user_info)
    
            recorded_after = int(player.get("after_mmr", 0) or 0)
            current = int(user_info.get("mmr", {}).get(role, 0) or 0)
            if recorded_after <= 0 or current != recorded_after:
                player["ai_mmr_late_skipped"] = True
                continue
    
            # 임시배치였던 경기에는 별도의 큰 보정을 적용한다.
            # 현재 active 여부가 아니라 "그 경기 당시 임시배치였는지"를 저장한 플래그를 사용한다.
            if bool(player.get("provisional_mmr")):
                score_row = score_by_uid.get(uid, {})
                display_score = float(
                    score_row.get("display_score",
                        score_row.get("expectation_score", score_row.get("score", 0))
                    ) or 0
                )
                own_team = str(player.get("team") or "")
                opponent_team = "red" if own_team == "blue" else "blue"
                opponent = player_by_team_role.get((opponent_team, str(role)))
                opponent_before = int((opponent or {}).get("before_mmr", 0) or 0)
    
                performance_adjustment = get_provisional_ai_performance_adjustment(display_score)
                opponent_adjustment = get_provisional_opponent_adjustment(
                    player.get("before_mmr", 0),
                    opponent_before,
                )
    
                old_signed_delta = int(player.get("delta", 0) or 0)
                desired_signed_delta = clamp_provisional_final_delta(
                    old_signed_delta,
                    performance_adjustment + opponent_adjustment,
                )
                adjustment = desired_signed_delta - old_signed_delta
    
                player["provisional_ai_score"] = round(display_score, 2)
                player["provisional_ai_performance_adjustment"] = int(performance_adjustment)
                player["provisional_opponent_adjustment"] = int(opponent_adjustment)
                player["provisional_ai_mmr_adjustment"] = int(adjustment)
                player["ai_mmr_adjustment"] = int(adjustment)
            else:
                adjustment = max(-AI_MMR_ADJUSTMENT_CAP, min(AI_MMR_ADJUSTMENT_CAP, int(adjustments.get(uid, 0) or 0)))
                team_adjustment = int(player.get("team_mmr_adjustment", 0) or 0)
                combined = max(
                    -TEAM_AI_COMBINED_ADJUSTMENT_CAP,
                    min(TEAM_AI_COMBINED_ADJUSTMENT_CAP, team_adjustment + adjustment),
                )
                adjustment = combined - team_adjustment
                player["ai_mmr_adjustment"] = adjustment
    
            if adjustment == 0:
                continue
    
            updated = max(0, current + adjustment)
            user_info["mmr"][role] = updated
            player["after_mmr"] = updated
            player["delta"] = int(player.get("delta", 0) or 0) + adjustment
            for undo_snapshot in bot.history.get(str(gid), {}).values():
                if str(undo_snapshot.get("match_id") or "") != match_id:
                    continue
                applied_deltas = undo_snapshot.setdefault("applied_deltas", {})
                applied_deltas[uid] = abs(int(player["delta"]))
                break
            update_peak_records(user_info)
            applied_any = True
    
        record[AI_MMR_APPLIED_KEY] = True
        record["ai_mmr_model"] = (
            "provisional_ai_opponent_v1"
            if any(bool(player.get("provisional_mmr")) for player in (record.get("players", []) or []))
            else "expectation_rank_v2"
        )
        if not applied_any:
            return []
    
        final_lines = []
        for player in record.get("players", []) or []:
            uid = str(player.get("user_id"))
            role = player.get("role")
            user_info = guild_data.get(uid)
            if not isinstance(user_info, dict) or role not in ROLES:
                continue
            current = int(ensure_user_format(user_info).get("mmr", {}).get(role, 0) or 0)
            final_lines.append(f"<@{uid}> `[{role}]` **{current}점**")
        return final_lines


    
    ALL_ROUNDER_PREF = "올라이너"
    role_choices = [app_commands.Choice(name=r, value=r) for r in ROLES]
    role_or_all_rounder_choices = [app_commands.Choice(name=ALL_ROUNDER_PREF, value=ALL_ROUNDER_PREF)] + role_choices
    win_target_choices = queue_choices + [
        app_commands.Choice(name=LEAGUE_SERIES_SIM_LABEL, value=LEAGUE_SERIES_SIM_QUEUE_KEY),
    ]
    start_manage_queue_choices = queue_choices + [
        app_commands.Choice(name=LEAGUE_SERIES_SIM_LABEL, value=LEAGUE_SERIES_SIM_QUEUE_KEY),
    ]
    reset_queue_choices = queue_choices + [
        app_commands.Choice(name=LEAGUE_SERIES_SIM_LABEL, value=LEAGUE_SERIES_SIM_QUEUE_KEY),
    ]
    simulation_queue_choices = (
        [app_commands.Choice(name=f"{i}번 큐", value=str(i)) for i in range(1, 6)]
        + [
            app_commands.Choice(name="노밴 모드", value="노밴 모드"),
            app_commands.Choice(name="저티어 큐", value="저티어 큐"),
            app_commands.Choice(name="아레나(3x6)", value="아레나(3x6)"),
            app_commands.Choice(name="칼바람 나락", value="칼바람 나락"),
            app_commands.Choice(name=LEAGUE_SERIES_MODE_NAME, value=LEAGUE_SERIES_MODE_NAME),
            app_commands.Choice(name=ARAM_LEAGUE_MODE_NAME, value=ARAM_LEAGUE_MODE_NAME),
        ]
    )
    
    match_reception_choices = [
        app_commands.Choice(name="열기", value="open"),
        app_commands.Choice(name="닫기", value="close"),
    ]
    
    
    start_manage_action_choices = [
        app_commands.Choice(name="대기", value="wait"),
        app_commands.Choice(name="해제", value="release"),
        app_commands.Choice(name="시작", value="start"),
        app_commands.Choice(name="팀구성", value="team_setup"),
    ]
    
    third_place_choices = [
        app_commands.Choice(name="끄기", value="off"),
        app_commands.Choice(name="켜기", value="on"),
    ]
    
    async def enable_start_wait(interaction: discord.Interaction, 큐: str):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        queue_key = normalize_queue_selector(큐)
        if queue_key is None:
            return await interaction.response.send_message(f"⚠️ 큐는 `1~5`, `노밴 모드`, `저티어 큐`, `아레나(3x6)`, `협곡 리그전`, `칼바람 나락`, `칼바람 리그전` 중에서 선택해주세요.", ephemeral=True)
        if queue_key in (LEAGUE_SIM_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY):
            return await interaction.response.send_message(f"🧪 {get_queue_label(queue_key)}은 `/내전진행 작업:팀구성 큐:{get_queue_label(queue_key)}` 으로만 시작할 수 있습니다.", ephemeral=True)
        feature_key = get_queue_feature_key(queue_key)
        if feature_key and not is_feature_enabled(gid, feature_key):
            return await interaction.response.send_message(get_disabled_feature_message(feature_key), ephemeral=True)
        if queue_key in (LEAGUE_SERIES_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY):
            return await interaction.response.send_message(f"🏆 {get_queue_label(queue_key)}은 `/내전진행 작업:시작 큐:{get_queue_label(queue_key)}` 또는 `작업:팀구성`으로 시작해주세요.", ephemeral=True)
        if queue_key == LEAGUE_QUEUE_KEY:
            return await interaction.response.send_message(f"🏆 {LEAGUE_MODE_NAME}은 `/협곡리그전팀구성` 명령어를 사용해주세요.", ephemeral=True)
    
        set_start_wait_enabled(gid, queue_key, True)
        set_reset_start_wait_enabled(gid, queue_key, False)
        count = len(ensure_guild_queues(gid).get(queue_key, []))
        required = get_required_count(queue_key)
        await interaction.response.send_message(
            f"⏸️ **{get_queue_label(queue_key)} 큐 시작대기 모드 ON**\n"
            f"대기열이 `{required}/{required}`명이 되어도 자동 라인업을 만들지 않습니다.\n"
            f"현재 인원: `{count}/{required}`\n"
            f"시작하려면 `/내전진행 작업:시작 큐:{get_queue_label(queue_key)}` 를 입력해주세요.",
            ephemeral=True
        )
    
    async def disable_start_wait(interaction: discord.Interaction, 큐: str):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        queue_key = normalize_queue_selector(큐)
        if queue_key is None:
            return await interaction.response.send_message(f"⚠️ 큐는 `1~5`, `노밴 모드`, `저티어 큐`, `아레나(3x6)`, `협곡 리그전`, `칼바람 나락`, `칼바람 리그전` 중에서 선택해주세요.", ephemeral=True)
        if queue_key in (LEAGUE_SIM_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY):
            return await interaction.response.send_message(f"🧪 {get_queue_label(queue_key)}은 시작대기 설정을 사용하지 않습니다. `/내전진행 작업:팀구성 큐:{get_queue_label(queue_key)}` 을 사용해주세요.", ephemeral=True)
        feature_key = get_queue_feature_key(queue_key)
        if feature_key and not is_feature_enabled(gid, feature_key):
            return await interaction.response.send_message(get_disabled_feature_message(feature_key), ephemeral=True)
    
        set_start_wait_enabled(gid, queue_key, False)
        set_reset_start_wait_enabled(gid, queue_key, False)
        await interaction.response.send_message(
            f"▶️ **{get_queue_label(queue_key)} 큐 시작대기 모드 OFF**\n"
            "이제 인원이 차면 기존처럼 자동으로 라인업을 생성합니다.",
            ephemeral=True
        )
    
    async def start_waiting_queue(interaction: discord.Interaction, 큐: str, third_place: bool = False):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        queue_key = normalize_queue_selector(큐)
        if queue_key is None:
            return await interaction.response.send_message(f"⚠️ 큐는 `1~5`, `노밴 모드`, `저티어 큐`, `아레나(3x6)`, `협곡 리그전`, `칼바람 나락`, `칼바람 리그전` 중에서 선택해주세요.", ephemeral=True)
        if queue_key == LEAGUE_SIM_QUEUE_KEY:
            return await interaction.response.send_message(f"🧪 {LEAGUE_SIM_LABEL}은 `/내전진행 작업:팀구성 큐:{LEAGUE_SIM_LABEL}` 으로 시작해주세요.", ephemeral=True)
        if queue_key == LEAGUE_SERIES_SIM_QUEUE_KEY:
            return await league_series_lineup_simulation(interaction, third_place=third_place)
        feature_key = get_queue_feature_key(queue_key)
        if feature_key and not is_feature_enabled(gid, feature_key):
            return await interaction.response.send_message(get_disabled_feature_message(feature_key), ephemeral=True)
        if queue_key == LEAGUE_SERIES_QUEUE_KEY:
            return await league_series_lineup(interaction, third_place=third_place)
        if queue_key == ARAM_LEAGUE_QUEUE_KEY:
            return await aram_league_series_lineup(interaction, third_place=third_place)
        if queue_key == LEAGUE_QUEUE_KEY:
            return await interaction.response.send_message(f"🏆 {LEAGUE_MODE_NAME}은 `/협곡리그전팀구성` 명령어를 사용해주세요.", ephemeral=True)
    
        active_state = bot.active_games.get(gid, {}).get(queue_key)
        if active_state:
            await interaction.response.defer(ephemeral=True)
            if active_state.get("mode") == EVENT_MODE_KEY:
                return await send_existing_arena_lineup(interaction, gid, queue_key, active_state)
            if active_state.get("mode") == ARAM_MODE_KEY:
                return await send_existing_aram_lineup(interaction, gid, queue_key, active_state)
            return await send_existing_classic_lineup(interaction, gid, queue_key, active_state)
    
        q = ensure_guild_queues(gid).get(queue_key, [])
        required = get_required_count(queue_key)
        if len(q) < required:
            return await interaction.response.send_message(
                f"❌ {get_queue_label(queue_key)} 큐 시작 실패: 인원 부족 ({len(q)}/{required})",
                ephemeral=True
            )
    
        await interaction.response.defer(thinking=True)
        await internal_lineup(interaction, queue_key)
    
    async def setup_tournament_teams_from_start_manage(interaction: discord.Interaction, 큐: str, third_place: bool = False):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        queue_key = normalize_queue_selector(큐)
        if queue_key == LEAGUE_SIM_QUEUE_KEY:
            return await league_lineup_simulation(interaction, create_session=True, include_queue_progress=False)
        if queue_key == LEAGUE_SERIES_SIM_QUEUE_KEY:
            return await league_series_lineup_simulation(interaction, third_place=third_place)
        if queue_key == LEAGUE_SERIES_QUEUE_KEY:
            return await league_series_lineup(interaction, third_place=third_place)
        if queue_key == ARAM_LEAGUE_QUEUE_KEY:
            return await aram_league_series_lineup(interaction, third_place=third_place)
        if queue_key == LEAGUE_QUEUE_KEY:
            return await league_series_lineup(interaction, third_place=third_place)
    
        queue_label = get_queue_label(queue_key) if queue_key is not None else str(큐)
        return await interaction.response.send_message(
            f"⚠️ 팀구성 작업은 `{LEAGUE_SERIES_MODE_NAME}`, `{ARAM_LEAGUE_MODE_NAME}` 또는 `{LEAGUE_SERIES_SIM_LABEL}` 큐에서만 사용할 수 있습니다. 선택한 큐: `{queue_label}`",
            ephemeral=True
        )
    
    @bot.tree.command(name="내전진행", description="[내전 관리자] 큐 시작대기 설정과 즉시 시작을 관리합니다.")
    @app_commands.choices(작업=start_manage_action_choices, 큐=start_manage_queue_choices, 삼사위전=third_place_choices)
    @app_commands.describe(삼사위전="리그전 팀구성/시작 시 3/4위전을 진행할지 선택합니다.")
    async def manage_queue_start(
        interaction: discord.Interaction,
        작업: app_commands.Choice[str],
        큐: str,
        삼사위전: app_commands.Choice[str] = None,
    ):
        third_place = bool(삼사위전 and 삼사위전.value == "on")
        if 작업.value == "wait":
            return await enable_start_wait(interaction, 큐)
        if 작업.value == "release":
            return await disable_start_wait(interaction, 큐)
        if 작업.value == "start":
            return await start_waiting_queue(interaction, 큐, third_place=third_place)
        if 작업.value == "team_setup":
            return await setup_tournament_teams_from_start_manage(interaction, 큐, third_place=third_place)
        await interaction.response.send_message("⚠️ 작업은 대기, 해제, 시작, 팀구성 중에서 선택해주세요.", ephemeral=True)
    
    @bot.tree.command(name="라인업", description="대기열 인원이 차면 팀을 배정합니다. 아레나 선택이 가능합니다.")
    @app_commands.choices(큐=queue_choices)
    async def manual_lineup(interaction: discord.Interaction, 큐: str):
        gid = str(interaction.guild_id)
        queue_key = normalize_queue_selector(큐)
        if queue_key is None:
            return await interaction.response.send_message(f"⚠️ 큐는 `1~5`, `노밴 모드`, `저티어 큐`, `아레나(3x6)`, `협곡 리그전`, `칼바람 나락`, `칼바람 리그전` 중에서 선택해주세요.", ephemeral=True)
        feature_key = get_queue_feature_key(queue_key)
        if feature_key and not is_feature_enabled(gid, feature_key):
            return await interaction.response.send_message(get_disabled_feature_message(feature_key), ephemeral=True)
        if queue_key in (LEAGUE_QUEUE_KEY, LEAGUE_SERIES_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY):
            active_state = bot.active_games.get(gid, {}).get(queue_key)
            if not active_state or active_state.get("finalized"):
                guide = f"`/내전진행 작업:팀구성 큐:{get_queue_label(queue_key)}`"
                return await interaction.response.send_message(
                    f"🏆 아직 진행 중인 {get_queue_label(queue_key)} 대진표가 없습니다.\n"
                    f"대진표 생성은 {guide} 에서 먼저 진행해주세요.",
                    ephemeral=True,
                )
            embed = (
                build_league_series_embed(interaction.guild, gid, active_state, title_suffix="진행 중 대진표")
                if queue_key in (LEAGUE_SERIES_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY) else
                build_existing_league_bracket_embed(interaction.guild, gid, active_state, title_suffix="진행 중 대진표")
            )
            embeds = [embed]
            if queue_key in (LEAGUE_SERIES_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY):
                matches = active_state.get("matches", {}) or {}
                teams_by_no = {
                    int(team.get("team_no")): team
                    for team in active_state.get("teams", [])
                    if team.get("team_no") is not None
                }
                for match_id in active_state.get("match_order", []):
                    match = matches.get(str(match_id), {})
                    if not is_series_match_playable(match, matches):
                        continue
                    detail_embed = build_league_series_match_detail_embed(
                        interaction.guild, gid, match, matches, teams_by_no, active_state
                    )
                    if detail_embed:
                        embeds.append(detail_embed)
            return await interaction.response.send_message(
                embeds=embeds[:10],
                allowed_mentions=discord.AllowedMentions.none(),
            )
    
        active_state = bot.active_games.get(gid, {}).get(queue_key)
        if active_state:
            await interaction.response.defer(ephemeral=True)
            if active_state.get("mode") == EVENT_MODE_KEY:
                return await send_existing_arena_lineup(interaction, gid, queue_key, active_state)
            if active_state.get("mode") == ARAM_MODE_KEY:
                return await send_existing_aram_lineup(interaction, gid, queue_key, active_state)
            return await send_existing_classic_lineup(interaction, gid, queue_key, active_state)
    
        q = bot.queues.get(gid, {}).get(queue_key, [])
        required_count = get_required_count(queue_key)
    
        if not is_match_admin(interaction):
            if len(q) >= required_count:
                return await interaction.response.send_message(
                    "🧩 아직 관리자가 확정한 라인업이 없습니다. 정원이 찼더라도 일반 유저는 팀 구성을 시작할 수 없습니다.",
                    ephemeral=True,
                )
            return await interaction.response.send_message(
                f"📋 아직 확정된 라인업이 없습니다. 현재 대기 인원은 **{len(q)}/{required_count}명**입니다.",
                ephemeral=True,
            )
    
        if len(q) < required_count:
            return await interaction.response.send_message(
                f"❌ 대기 인원이 부족하여 팀을 생성할 수 없습니다. 현재 ({len(q)}/{required_count})명", 
                ephemeral=True
            )
        await interaction.response.defer(thinking=True)
        await internal_lineup(interaction, queue_key)
    
    async def send_streaming_simulation(interaction: discord.Interaction):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        embed = discord.Embed(
            title="📡 스트리밍 참가 알림 시뮬레이션",
            description="치지직 채팅에서 참가 신청이 들어왔을 때 디스코드에 보이는 알림 예시입니다. 실제 큐에는 반영되지 않습니다.",
            color=0x00ffa3,
        )
        embed.add_field(
            name="채팅 참가 신청",
            value=(
                "**치지직 채팅**\n"
                "`참가자루시드: 다이아3 탑 미드`\n\n"
                "**디스코드 알림**\n"
                "📡 **치지직 참가 신청**\n"
                "`참가자루시드` 님이 **1번 큐**에 참가했습니다.\n"
                "지망: **탑 / 정글** · 현재 인원 **6/10**"
            ),
            inline=False,
        )
        embed.add_field(
            name="특정 큐 참가 신청",
            value=(
                "**치지직 채팅**\n"
                "`금빛원딜: 원딜(D3) 서폿(P4)`\n\n"
                "**디스코드 알림**\n"
                "📡 **치지직 참가 신청**\n"
                "`금빛원딜` 님이 **2번 큐**에 자동 예약되었습니다.\n"
                "지망: **원딜 / 서폿** · 현재 인원 **1/10**"
            ),
            inline=False,
        )
        embed.add_field(
            name="정원 도달 알림",
            value=(
                "✅ **1번 큐 정원 도달**\n"
                "치지직 참가 신청으로 1번 큐가 **10/10명**이 되었습니다.\n"
                "다음 참가자부터는 큐 번호를 입력하지 않아도 **2번 큐**로 자동 예약됩니다.\n"
                "시작대기 ON이면 관리자의 `/내전진행 작업:시작`을 기다리고, OFF면 자동 라인업을 생성합니다."
            ),
            inline=False,
        )
        embed.add_field(
            name="채팅 응답 예시",
            value=(
                "`[루시드봇] 참가자루시드 참가 완료 · 1번 큐 6/10 · 탑/정글`\n"
                "`[루시드봇] 금빛원딜 참가 완료 · 2번 큐 1/10 · 원딜/서폿`"
            ),
            inline=False,
        )
        embed.set_footer(text="채팅 명령 사용법은 스트리밍 도움말에 있고, 이 화면은 운영자가 보게 될 알림 모양만 보여줍니다.")
        gid = str(interaction.guild_id)
        await send_league_sim_output(interaction, gid, embed=embed)
    
    simulation_choices = [
        app_commands.Choice(name="라인업", value="라인업"),
        app_commands.Choice(name="대기열", value="대기열"),
        app_commands.Choice(name="스트리밍", value="스트리밍"),
    ]
    
    @bot.tree.command(name="시뮬레이션", description="[내전 관리자] 선택한 큐의 라인업/대기열/스트리밍 흐름을 저장 없이 미리 확인합니다.")
    @app_commands.choices(큐=simulation_queue_choices)
    @app_commands.choices(종류=simulation_choices)
    @app_commands.describe(
        큐="라인업/대기열 시뮬레이션 대상 큐입니다. 스트리밍 선택 시에는 무시됩니다.",
        종류="라인업, 대기열, 스트리밍 중 확인할 흐름입니다."
    )
    async def simulation_command(interaction: discord.Interaction, 큐: str, 종류: app_commands.Choice[str]):
        queue_key = normalize_queue_selector(큐)
        if 종류.value == "라인업":
            if queue_key == LEAGUE_QUEUE_KEY:
                return await league_lineup_simulation(interaction, queue_only=True, prepare_queue=True, include_queue_progress=False)
            if queue_key == LEAGUE_SERIES_QUEUE_KEY:
                return await league_series_lineup_simulation(interaction)
            return await send_lineup_format_simulation(interaction, 큐, force_dummy=True)
        if 종류.value == "대기열":
            if queue_key == LEAGUE_QUEUE_KEY:
                return await league_lineup_simulation(interaction, queue_only=True, prepare_queue=True)
            return await send_queue_progress_simulation(interaction, 큐)
        if 종류.value == "스트리밍":
            return await send_streaming_simulation(interaction)
        await interaction.response.send_message("⚠️ 알 수 없는 시뮬레이션 종류입니다.", ephemeral=True)
    
    async def send_queue_progress_simulation(interaction: discord.Interaction, 큐: str):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        queue_key = normalize_queue_selector(큐)
        if queue_key is None:
            return await interaction.response.send_message(f"⚠️ 큐는 `1~5`, `노밴 모드`, `저티어 큐`, `아레나(3x6)`, `협곡 리그전`, `칼바람 나락`, `칼바람 리그전` 중에서 선택해주세요.", ephemeral=True)
    
        required = get_required_count(queue_key)
        role_cycle = list(ROLES)
        lines = []
        tier_counts = {}
        for idx in range(1, required + 1):
            role = role_cycle[(idx - 1) % len(role_cycle)]
            score = random.randint(800, 3200)
            tier_name = get_tier_name(score)
            tier_emoji = get_tier_emoji(tier_name, interaction.guild, gid)
            tier_counts[tier_emoji] = tier_counts.get(tier_emoji, 0) + 1
            filled = "■" * idx
            empty = "□" * (required - idx)
            pref_text = (
                "라인 선택 없음"
                if queue_key in (ARENA_QUEUE_NUM, ARAM_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY)
                else f"1지망 {get_role_display_marker(role, interaction.guild)}"
            )
            lines.append(f"`{idx:02}/{required}` {filled}{empty} {pref_text} `{get_public_mmr_rank(score)}` {tier_emoji} · 소환사 {idx}")
    
        dist_text = "  ".join(f"{emoji} x{count}" for emoji, count in tier_counts.items())
        embed = discord.Embed(
            title=f"🧪 {get_queue_label(queue_key)} 대기열 시뮬레이션",
            description="\n".join(lines),
            color=0x2ecc71,
        )
        embed.add_field(name="티어 분포", value=dist_text or "기록 없음", inline=False)
        if queue_key == ARENA_QUEUE_NUM:
            embed.add_field(name="구성 안내", value=f"`3인 x 6팀` 신청 **{required}/{required}명** · 정원 도달 시 아레나 팀 구성이 가능합니다.", inline=False)
        elif queue_key == ARAM_QUEUE_KEY:
            embed.add_field(name="구성 안내", value=f"`5v5` 신청 **{required}/{required}명** · 최고 티어 MMR 기준으로 블루/레드 팀을 구성합니다.", inline=False)
        else:
            embed.add_field(name="구성 안내", value=f"`5v5` 신청 **{required}/{required}명** · 시작대기 OFF면 자동 라인업, ON이면 운영자 시작을 기다립니다.", inline=False)
        embed.set_footer(text="시뮬레이션 화면입니다. 실제 대기열, 전적, 음성 채널에는 반영되지 않습니다.")
        await send_league_sim_output(interaction, gid, embed=embed)
    
    @bot.tree.command(name="라인업테스트", description="[내전 관리자] 새 라인업 표시 포맷을 미리 확인합니다.")
    @app_commands.choices(큐=queue_choices)
    async def lineup_format_test(interaction: discord.Interaction, 큐: str):
        return await send_lineup_format_simulation(interaction, 큐, force_dummy=False)
    
    async def send_arena_lineup_format_simulation(interaction: discord.Interaction, queue_key, force_dummy: bool = False):
        gid = str(interaction.guild_id)
        players = build_dummy_arena_test_players() if force_dummy else build_arena_test_players_from_user_data(interaction.guild, gid)
        if not players:
            players = build_dummy_arena_test_players()
            force_dummy = True
    
        teams = build_arena_test_teams(gid, players)
        if not teams:
            return await interaction.response.send_message(
                "⚠️ 현재 인원 구성과 팀 분리 조건으로 아레나 시뮬레이션 팀을 만들 수 없습니다.",
                ephemeral=True
            )
    
        await interaction.response.defer(ephemeral=True)
        embed = build_arena_test_embed(queue_key, teams, force_dummy=force_dummy, guild=interaction.guild, gid=gid)
        return await send_or_edit_arena_reveal(
            interaction,
            gid,
            teams,
            embed,
            simulation=True,
            use_output_channel=False
        )
    
    async def send_lineup_format_simulation(interaction: discord.Interaction, 큐: str, force_dummy: bool = False):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        queue_key = normalize_queue_selector(큐)
        if queue_key is None:
            return await interaction.response.send_message(f"⚠️ 큐는 `1~5`, `노밴 모드`, `저티어 큐`, `아레나(3x6)`, `협곡 리그전`, `칼바람 나락`, `칼바람 리그전` 중에서 선택해주세요.", ephemeral=True)
    
        if queue_key == ARENA_QUEUE_NUM:
            return await send_arena_lineup_format_simulation(interaction, queue_key, force_dummy=force_dummy)
    
        # 실제 안전성 탐색은 수 초 걸릴 수 있으므로 Discord의 3초 interaction 제한 전에 먼저 ACK한다.
        # 이후 send_league_sim_output()은 response.is_done()을 보고 followup으로 결과를 전송한다.
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
    
        active_state = bot.active_games.get(gid, {}).get(queue_key)
        if False and active_state and active_state.get("mode") not in (EVENT_MODE_KEY, ARAM_MODE_KEY, LEAGUE_MODE_KEY):
            roles_map = active_state.get("roles", {})
    
            def build_team(team_key):
                team = []
                for role in ROLES:
                    uid = next((str(uid) for uid in active_state.get(team_key, []) if roles_map.get(str(uid)) == role), None)
                    if not uid:
                        continue
                    member = interaction.guild.get_member(int(uid)) if interaction.guild else None
                    user_info = ensure_user_format(bot.user_data.get(gid, {}).get(uid, make_default_user(f"UID {uid}")))
                    score = get_noban_queue_score(user_info, role) if active_state.get("mode") == NOBAN_MODE_KEY else user_info['mmr'].get(role, 0)
                    team.append((member or uid, role, score, score))
                return team
    
            blue_team = build_team("blue")
            red_team = build_team("red")
            if len(blue_team) == len(ROLES) and len(red_team) == len(ROLES):
                blue_avg = int(sum(item[3] for item in blue_team) / len(blue_team))
                red_avg = int(sum(item[3] for item in red_team) / len(red_team))
                avg_diff = blue_avg - red_avg
                if avg_diff == 0:
                    team_gap_text = "⚪ 팀 평균 동률"
                elif avg_diff > 0:
                    team_gap_text = f"🔵 BLUE TEAM +{avg_diff}"
                else:
                    team_gap_text = f"🔴 RED TEAM +{abs(avg_diff)}"
                embed = discord.Embed(
                    title=f"🧪 {get_queue_label(queue_key)} 큐 라인업 포맷 테스트",
                    color=0x95a5a6,
                )
                title_overrides = build_lineup_test_title_overrides(blue_team, red_team)
                apply_classic_lineup_embed(embed, interaction.guild, gid, blue_team, red_team, blue_avg, red_avg, team_gap_text, title_overrides)
                embed.set_footer(text="테스트 출력입니다. 팀 재계산/음성 이동은 실행하지 않습니다.")
                summary_embed = build_classic_power_summary_embed(interaction.guild, gid, queue_key, blue_team, red_team, test_mode=True)
                return await interaction.response.send_message(embeds=[summary_embed, embed], ephemeral=True)
    
        test_failure_reason = None
        if force_dummy:
            blue_team, red_team = build_dummy_lineup_test_teams()
        else:
            blue_team, red_team, test_failure_reason = build_lineup_test_teams_from_user_data(interaction.guild, gid, queue_key)
        if blue_team and red_team:
            blue_avg = int(sum(item[3] for item in blue_team) / len(blue_team))
            red_avg = int(sum(item[3] for item in red_team) / len(red_team))
            avg_diff = blue_avg - red_avg
            if avg_diff == 0:
                team_gap_text = "⚪ 팀 평균 동률"
            elif avg_diff > 0:
                team_gap_text = f"🔵 BLUE TEAM +{avg_diff}"
            else:
                team_gap_text = f"🔴 RED TEAM +{abs(avg_diff)}"
            embed = discord.Embed(
                title=f"🧪 {get_queue_label(queue_key)} 큐 라인업 포맷 테스트",
                color=0x95a5a6,
            )
            title_overrides = build_lineup_test_title_overrides(blue_team, red_team)
            apply_classic_lineup_embed(embed, interaction.guild, gid, blue_team, red_team, blue_avg, red_avg, team_gap_text, title_overrides)
            footer_text = (
                "소환사 1~10과 랜덤 점수(800~3200점)로 만든 샘플입니다. 팀 재계산/음성 이동은 실행하지 않습니다."
                if force_dummy else
                "서버에서 랜덤 10명을 1회 고정 선정한 뒤, 그 10명 안에서 MMR2.1 유효 전력 + 실제 안전성 검사를 통과한 최적 팀을 찾은 테스트입니다. 대기열/전적/음성 채널에는 반영되지 않습니다."
            )
            embed.set_footer(text=footer_text)
            summary_embed = build_classic_power_summary_embed(interaction.guild, gid, queue_key, blue_team, red_team, test_mode=True)
            return await send_league_sim_output(interaction, gid, embeds=[summary_embed, embed])
    
        if not force_dummy:
            reason = test_failure_reason or "실제 매칭 안전성 조건을 통과하는 라인업을 만들지 못했습니다."
            return await send_league_sim_output(
                interaction,
                gid,
                content=(
                    "⚠️ **안전한 테스트 라인업 생성 실패**\n"
                    f"{reason}\n"
                    f"현재 테스트도 실제 라인 제외 기준(일반 {LANE_EXCLUSION_GAP}점"
                    f"{f' / 초기 서버 {EARLY_SERVER_LANE_EXCLUSION_GAP}점' if is_early_match_history_server(gid) else ''})과 "
                    "MMR2.1 유효 전력 검사를 적용합니다."
                ),
            )
    
        summary_embed = discord.Embed(
            title=f"⚔️ 🧪 포맷 테스트 · {get_queue_label(queue_key)} 큐 매치 라인업",
            description=(
                "**📊 양 팀 전력 비교**\n"
                "🔵 [██████░░░░] 🔴\n"
                "⚖️ 전력 분석: 블루팀이 살짝 앞서지만 적당한 차이입니다."
            ),
            color=0x2b2d31,
        )
        summary_embed.add_field(name="🔵 BLUE 평균", value=f"**{get_public_mmr_rank(1648)}**", inline=True)
        summary_embed.add_field(name="🔴 RED 평균", value=f"**{get_public_mmr_rank(1589)}**", inline=True)
        summary_embed.set_footer(text="실제 유저 데이터가 라인별 2명 이상 부족해 샘플을 표시했습니다.")
    
        embed = discord.Embed(
            title="🧪 라인업 포맷 샘플",
            description="⚔️ **라인별 매치업**",
            color=0x95a5a6,
        )
        embed.add_field(
            name="🔵 BLUE TEAM · 총점 `8241점`",
            value=(
                "**[탑]** 샘플블루탑 🟢 `1822점` `🔧 가성비의 표본`\n"
                "**[정글]** 샘플블루정글 🔵 `1480점`\n"
                "**[미드]** 샘플블루미드 🔵 `1235점` `🌱 새싹`\n"
                "**[원딜]** 샘플블루원딜 🟣 `2206점` `🏆 그랜드마스터의 위엄`\n"
                "**[서폿]** 샘플블루서폿 🔵 `1498점`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔴 RED TEAM · 총점 `7948점`",
            value=(
                "**[탑]** 샘플레드탑 🔵 `1447점`\n"
                "**[정글]** 샘플레드정글 🟠 `1818점` `✨ 마지막 불빛`\n"
                "**[미드]** 샘플레드미드 🔵 `1450점` `⚔️ 이름을 건 승부`\n"
                "**[원딜]** 샘플레드원딜 🟣 `1907점` `⭐ 챌린저의 별`\n"
                "**[서폿]** 샘플레드서폿 🔵 `1326점`"
            ),
            inline=False,
        )
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="📈 팀 평균", value="BLUE `1648점` vs RED `1589점`\n🔵 BLUE TEAM +59", inline=False)
        embed.add_field(
            name="📊 라인별 우세",
            value=(
                "**[탑]** `1822 VS 1447` 🔵 B+375\n"
                "**[정글]** `1480 VS 1818` 🔴 R+338\n"
                "**[미드]** `1235 VS 1450` 🔴 R+215\n"
                "**[원딜]** `2206 VS 1907` 🔵 B+299\n"
                "**[서폿]** `1498 VS 1326` 🔵 B+172"
            ),
            inline=False,
        )
        embed.set_footer(text="실제 유저 데이터가 라인별 2명 이상 부족해 샘플을 표시했습니다.")
        await send_league_sim_output(interaction, gid, embeds=[summary_embed, embed])
    
    # ==============================================================================
    # [3. 핵심 포지션 매칭 및 밸런싱 백엔드 엔진 - 규칙 및 최적화 하이브리드 로직]
    # ==============================================================================
    
    async def send_existing_classic_lineup(interaction, gid, q_num, game_state):
        roles_map = game_state.get("roles", {})
    
        def build_team(team_key):
            team = []
            for role in ROLES:
                uid = next((str(uid) for uid in game_state.get(team_key, []) if roles_map.get(str(uid)) == role), None)
                if not uid:
                    continue
                member = interaction.guild.get_member(int(uid)) if interaction.guild else None
                user_info = ensure_user_format(bot.user_data.get(gid, {}).get(uid, make_default_user(f"UID {uid}")))
                if game_state.get("mode") == NOBAN_MODE_KEY:
                    score = get_noban_queue_score(user_info, role)
                else:
                    score = user_info['mmr'].get(role, 0)
                team.append((member or uid, role, score, score))
            return team
    
        blue_team = build_team("blue")
        red_team = build_team("red")
        blue_avg = int(sum(item[3] for item in blue_team) / len(blue_team)) if blue_team else 0
        red_avg = int(sum(item[3] for item in red_team) / len(red_team)) if red_team else 0
        avg_diff = blue_avg - red_avg
        if avg_diff == 0:
            team_gap_text = "⚪ 팀 평균 동률"
        elif avg_diff > 0:
            team_gap_text = f"🔵 BLUE TEAM +{avg_diff}"
        else:
            team_gap_text = f"🔴 RED TEAM +{abs(avg_diff)}"
    
        embed = discord.Embed(
            title=f"⚔️ {get_queue_label(q_num)} 큐 기존 라인업",
            description="이미 구성된 팀을 다시 표시합니다. 팀 재계산과 음성채널 이동은 실행하지 않았습니다.",
            color=0x2b2d31
        )
        if len(blue_team) == len(ROLES) and len(red_team) == len(ROLES):
            apply_classic_lineup_embed(embed, interaction.guild, gid, blue_team, red_team, blue_avg, red_avg, team_gap_text)
            embed.description = "이미 구성된 팀을 다시 표시합니다. 팀 재계산과 음성채널 이동은 실행하지 않았습니다.\n\n" + (embed.description or "")
        else:
            embed.description += "\n\n기존 라인업 데이터가 일부 누락되어 라인별 매치업을 만들 수 없습니다."
    
        matchups = []
        for role in ROLES:
            blue_uid = next((str(uid) for uid in game_state.get("blue", []) if roles_map.get(str(uid)) == role), None)
            red_uid = next((str(uid) for uid in game_state.get("red", []) if roles_map.get(str(uid)) == role), None)
            if not blue_uid or not red_uid:
                continue
    
            blue_info = ensure_user_format(bot.user_data.get(gid, {}).get(blue_uid, make_default_user(f"UID {blue_uid}")))
            red_info = ensure_user_format(bot.user_data.get(gid, {}).get(red_uid, make_default_user(f"UID {red_uid}")))
            matchups.append({
                "role": role,
                "blue_label": get_member_label(interaction.guild, gid, blue_uid),
                "red_label": get_member_label(interaction.guild, gid, red_uid),
                "blue_mmr": blue_info['mmr'].get(role, 0),
                "red_mmr": red_info['mmr'].get(role, 0),
            })
    
        warning_text = build_match_quality_warning(matchups, gid)
        if warning_text:
            embed.add_field(name="🚨 매칭 품질 안내", value=warning_text, inline=False)
    
        await send_match_output(interaction, gid, embed=embed)
    
    async def send_classic_lineup_dm_notifications(gid, q_num, blue_team, red_team, embeds):
        queue_label = get_queue_label(q_num)
        content = (
            f"📣 **{queue_label} 큐가 매칭되었습니다!**\n"
            "아래 라인업을 확인하고 음성채널로 이동해주세요."
        )
        failed = []
        mention_replacements = {}
        for user, _, _, _ in blue_team + red_team:
            uid = str(user.id)
            name = compact_riot_name(get_registered_display_name(None, gid, uid)) or getattr(user, "display_name", uid)
            mention_replacements[f"<@{uid}>"] = name
            mention_replacements[f"<@!{uid}>"] = name
    
        def replace_lineup_mentions(text):
            text = str(text or "")
            for mention, name in mention_replacements.items():
                text = text.replace(mention, name)
            return text
    
        def make_dm_embed(embed):
            dm_embed = embed.copy()
            if dm_embed.title:
                dm_embed.title = replace_lineup_mentions(dm_embed.title)
            if dm_embed.description:
                dm_embed.description = replace_lineup_mentions(dm_embed.description)
            for index in range(len(dm_embed.fields) - 1, -1, -1):
                field = dm_embed.fields[index]
                if "팀 평균" in str(field.name):
                    dm_embed.remove_field(index)
            for index, field in enumerate(dm_embed.fields):
                dm_embed.set_field_at(
                    index,
                    name=replace_lineup_mentions(field.name),
                    value=replace_lineup_mentions(field.value),
                    inline=field.inline
                )
            return dm_embed
    
        for user, _, _, _ in blue_team + red_team:
            try:
                dm_embeds = [make_dm_embed(embed) for embed in embeds if embed]
                await user.send(content=content, embeds=dm_embeds, allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.HTTPException):
                failed.append(getattr(user, "display_name", str(user)))
    
        return failed
    
    async def send_existing_arena_lineup(interaction, gid, q_num, game_state):
        embed = discord.Embed(
            title=f"🏟️ {q_num}번 큐 기존 아레나 라인업",
            description="이미 구성된 아레나 팀을 다시 표시합니다.",
            color=0xf39c12
        )
        for team in game_state.get("teams", []):
            members = [get_member_label(interaction.guild, gid, uid) for uid in team.get("players", [])]
            embed.add_field(
                name=f"{team.get('name', '아레나 팀')} · 총점 {team.get('total', 0)}",
                value="\n".join(members) if members else "기록 없음",
                inline=False
            )
        await send_match_output(interaction, gid, embed=embed)
    
    async def send_existing_aram_lineup(interaction, gid, q_num, game_state):
        embed = discord.Embed(
            title="🎲 기존 칼바람 나락 라인업",
            description="이미 구성된 총력전 팀을 다시 표시합니다. 팀 재계산은 실행하지 않았습니다.",
            color=0x1abc9c
        )
        for key, label in (("blue", "🔵 BLUE TEAM"), ("red", "🔴 RED TEAM")):
            lines = []
            for uid in game_state.get(key, []):
                member = interaction.guild.get_member(int(uid)) if interaction.guild else None
                mention = member.mention if member else f"<@{uid}>"
                user_info = ensure_user_format(bot.user_data.get(gid, {}).get(str(uid), make_default_user(f"UID {uid}")))
                peak = get_peak_mmr(user_info['mmr'])
                tier = get_tier_name(peak)
                lines.append(f"{mention} · {peak}점 {get_tier_emoji(tier, interaction.guild, gid)}")
            embed.add_field(name=label, value="\n".join(lines) if lines else "기록 없음", inline=False)
        await send_match_output(interaction, gid, embed=embed)
    
    async def get_or_create_match_category(guild):
        gid = str(getattr(guild, "id", "") or "")
        category_id = bot.user_data.get(gid, {}).get(MATCH_VOICE_CATEGORY_KEY)
        if category_id:
            try:
                category = guild.get_channel(int(category_id))
                if isinstance(category, discord.CategoryChannel):
                    return category
            except (TypeError, ValueError):
                pass
        for channel_key in (MATCH_OUTPUT_CHANNEL_KEY, PARTICIPATION_CHANNEL_KEY, PARTY_CHANNEL_KEY):
            channel_id = bot.user_data.get(gid, {}).get(channel_key)
            if not channel_id:
                continue
            try:
                channel = guild.get_channel(int(channel_id))
            except (TypeError, ValueError):
                continue
            category = getattr(channel, "category", None)
            if isinstance(category, discord.CategoryChannel):
                if gid:
                    bot.user_data.setdefault(gid, {})[MATCH_VOICE_CATEGORY_KEY] = str(category.id)
                    bot.save_lucid_data(gid)
                return category
        category = (
            discord.utils.get(guild.categories, name="⚔️ 내전")
            or discord.utils.get(guild.categories, name="내전 채널")
            or discord.utils.get(guild.categories, name="내전 카테고리")
        )
        if category:
            if gid:
                bot.user_data.setdefault(gid, {})[MATCH_VOICE_CATEGORY_KEY] = str(category.id)
                bot.save_lucid_data(gid)
            return category
        try:
            category = await guild.create_category("내전 카테고리")
            if gid:
                bot.user_data.setdefault(gid, {})[MATCH_VOICE_CATEGORY_KEY] = str(category.id)
                bot.save_lucid_data(gid)
            return category
        except Exception as e:
            print(f"🔊 내전 카테고리 생성 실패: {e}")
            return None
    
    async def move_member_to_voice_verified(member, target, *, reason=None):
        target_id = getattr(target, "id", None)
        last_error = None
        for attempt in range(2):
            current = getattr(getattr(member, "voice", None), "channel", None)
            if target_id is not None and getattr(current, "id", None) == target_id:
                return True
            try:
                kwargs = {"reason": reason} if reason else {}
                await member.move_to(target, **kwargs)
            except Exception as exc:
                last_error = exc
            await asyncio.sleep(TEAM_VOICE_MOVE_VERIFY_SECONDS)
            current = getattr(getattr(member, "voice", None), "channel", None)
            if target_id is not None and getattr(current, "id", None) == target_id:
                return True

        logger.warning(
            "팀 음성 이동 최종 확인 실패: member_id=%s target_channel_id=%s error=%s",
            getattr(member, "id", None),
            target_id,
            last_error,
        )
        return False

    async def create_and_move_team_voice_channels(
        guild,
        team_specs,
        *,
        move_members=True,
        game_state=None,
        include_waiting=False,
    ):
        _sync_runtime()
        category = await get_or_create_match_category(guild)
        created_channels = []
        move_targets = []
        try:
            for channel_name, users in team_specs:
                vc = discord.utils.get(guild.voice_channels, name=channel_name)
                if not vc:
                    vc = await guild.create_voice_channel(channel_name, category=category)
                created_channels.append(vc)
                if isinstance(game_state, dict):
                    game_state.setdefault("voice_channels", {})[_voice_state_key(channel_name, len(created_channels) - 1)] = int(vc.id)
                if move_members:
                    move_targets.extend((user, vc) for user in users)

            if include_waiting:
                waiting_vc = discord.utils.get(category.voice_channels, name="내전 대기실")
                if not waiting_vc:
                    waiting_vc = discord.utils.get(guild.voice_channels, name="내전 대기실")
                if not waiting_vc:
                    waiting_vc = await guild.create_voice_channel("내전 대기실", category=category)
                created_channels.append(waiting_vc)
                if isinstance(game_state, dict):
                    game_state.setdefault("voice_channels", {})["waiting"] = int(waiting_vc.id)

            if move_members and move_targets:
                # Let Discord publish both newly created channels before voice-state moves begin.
                await asyncio.sleep(TEAM_VOICE_CHANNEL_SETTLE_SECONDS)
                connected_targets = [
                    (user, vc) for user, vc in move_targets
                    if user and user.voice and user.voice.channel
                ]
                for index, (user, vc) in enumerate(connected_targets):
                    await move_member_to_voice_verified(user, vc)
                    if index + 1 < len(connected_targets):
                        await asyncio.sleep(TEAM_VOICE_MOVE_INTERVAL_SECONDS)
        except Exception as e:
            print(f"🔊 팀 음성 채널 제어 예외 스킵 처리: {e}")
        if isinstance(game_state, dict):
            _persist_active_game(getattr(guild, "id", None), game_state)
        return created_channels
    
    async def move_members_to_waiting_voice(guild, user_ids, *, waiting_channel_id=None):
        category = await get_or_create_match_category(guild)
        if not category:
            logger.warning("경기 종료 이동 실패: 내전 카테고리를 찾지 못했습니다. guild_id=%s", getattr(guild, "id", None))
            return 0

        waiting_vc = None
        if waiting_channel_id is not None and hasattr(guild, "get_channel"):
            try:
                waiting_vc = guild.get_channel(int(waiting_channel_id))
            except (TypeError, ValueError):
                waiting_vc = None
        waiting_vc = waiting_vc or discord.utils.get(category.voice_channels, name="내전 대기실")
        if not waiting_vc:
            # Also reuse an existing waiting room elsewhere in the guild before
            # creating a duplicate in another category.
            waiting_vc = discord.utils.get(guild.voice_channels, name="내전 대기실")

        if not waiting_vc:
            try:
                waiting_vc = await guild.create_voice_channel("내전 대기실", category=category)
            except Exception as exc:
                logger.exception(
                    "경기 종료 이동 실패: 내전 대기실 생성 실패 guild_id=%s error=%s",
                    getattr(guild, "id", None),
                    exc,
                )
                return 0

        moved_count = 0
        connected_count = 0
        missing_count = 0
        failed_count = 0

        for uid in set(map(str, user_ids or [])):
            try:
                uid_int = int(uid)
            except (TypeError, ValueError):
                missing_count += 1
                continue

            member = guild.get_member(uid_int)
            if member is None:
                try:
                    member = await guild.fetch_member(uid_int)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    member = None

            if member is None:
                missing_count += 1
                continue

            voice_state = getattr(member, "voice", None)
            current_vc = getattr(voice_state, "channel", None)
            if current_vc is None:
                continue

            connected_count += 1

            # Already in waiting room counts as successfully settled.
            if current_vc.id == waiting_vc.id:
                moved_count += 1
                continue

            if await move_member_to_voice_verified(member, waiting_vc, reason="내전 경기 종료"):
                moved_count += 1
            else:
                failed_count += 1
                logger.warning(
                    "경기 종료 대기실 이동 실패: guild_id=%s user_id=%s from_channel=%s to_channel=%s",
                    getattr(guild, "id", None),
                    uid_int,
                    getattr(current_vc, "id", None),
                    getattr(waiting_vc, "id", None),
                )

        logger.info(
            "경기 종료 음성 이동 결과: guild_id=%s waiting_channel_id=%s participants=%s connected=%s moved=%s missing=%s failed=%s",
            getattr(guild, "id", None),
            getattr(waiting_vc, "id", None),
            len(set(map(str, user_ids or []))),
            connected_count,
            moved_count,
            missing_count,
            failed_count,
        )
        return moved_count

    async def move_stored_league_teams_to_existing_voice_channels(guild, teams, *, mode_name=LEAGUE_MODE_NAME):
        for team in teams:
            channel_name = f"🏆 {mode_name} {team['team_no']}팀"
            vc = discord.utils.get(guild.voice_channels, name=channel_name)
            if not vc:
                continue
            for uid in team.get("players", []):
                try:
                    member = guild.get_member(int(uid))
                except (TypeError, ValueError):
                    member = None
                if member and member.voice and member.voice.channel:
                    await move_member_to_voice_verified(member, vc)
    
    def get_classic_voice_channel_names(q_num):
        if q_num == NOBAN_QUEUE_NUM:
            return "🚫 노밴 모드 - 블루팀", "🚫 노밴 모드 - 레드팀"
        if q_num == LOW_TIER_QUEUE_KEY:
            return f"🔵 {LOW_TIER_MODE_NAME} - 블루팀", f"🔴 {LOW_TIER_MODE_NAME} - 레드팀"
        queue_label = get_queue_label(q_num)
        return f"🔵 큐 {queue_label} - 블루팀", f"🔴 큐 {queue_label} - 레드팀"

    def choose_aram_blue_team(gid, uids, score_by_uid):
        candidates = []
        for blue_uids in itertools.combinations(uids, 5):
            if uids[0] not in blue_uids:  # 같은 두 팀을 BLUE/RED만 바꾼 중복 조합은 제외한다.
                continue
            red_uids = [uid for uid in uids if uid not in blue_uids]
            if team_violates_separation(gid, blue_uids) or team_violates_separation(gid, red_uids):
                continue
            diff = abs(sum(score_by_uid[uid] for uid in blue_uids) - sum(score_by_uid[uid] for uid in red_uids))
            candidates.append((diff, frozenset(blue_uids)))

        if not candidates:
            return None, None

        candidates.sort(key=lambda item: item[0])
        min_diff = candidates[0][0]
        balanced = [item for item in candidates if item[0] <= min_diff + 100]

        player_set = frozenset(uids)
        previous_partition = None
        for record in reversed(bot.user_data.get(gid, {}).get(MATCH_HISTORY_KEY, [])):
            if record.get("cancelled") or record.get("mode") != ARAM_MODE_KEY:
                continue
            record_players = record.get("players", []) or []
            record_ids = frozenset(str(player.get("user_id")) for player in record_players)
            if record_ids != player_set:
                continue
            previous_blue = frozenset(
                str(player.get("user_id")) for player in record_players if player.get("team") == "blue"
            )
            previous_partition = frozenset((previous_blue, player_set - previous_blue))
            break

        alternatives = [
            item for item in balanced
            if frozenset((item[1], player_set - item[1])) != previous_partition
        ]
        chosen_diff, blue_team = random.choice(alternatives or balanced)
        if random.random() < 0.5:
            blue_team = player_set - blue_team
        return set(blue_team), chosen_diff
    
    async def internal_arena_lineup(interaction: discord.Interaction, q_num: int):
        gid = str(interaction.guild_id)
        q = bot.queues.get(gid, {}).get(q_num, [])
    
        if len(q) < ARENA_PLAYER_COUNT:
            msg = f"❌ 아레나(3x6) 매칭 구성 실패: 인원 부족 ({len(q)}/{ARENA_PLAYER_COUNT})"
            if not interaction.response.is_done():
                return await interaction.response.send_message(msg)
            return await interaction.followup.send(msg)
    
        if not interaction.response.is_done():
            await interaction.response.defer()
    
        players = []
        for data in q[:ARENA_PLAYER_COUNT]:
            user = data[0]
            raw_info = bot.user_data.get(gid, {}).get(str(user.id), {'mmr': 0, 'lol_name': user.display_name})
            user_info = ensure_user_format(raw_info)
            peak_mmr = get_peak_mmr(user_info['mmr'])
            tier_name = get_tier_name(peak_mmr)
            players.append({
                "user": user,
                "uid": str(user.id),
                "name": user_info.get('lol_name', user.display_name),
                "score": peak_mmr,
                "tier": tier_name,
            })
    
        players.sort(key=lambda item: item["score"], reverse=True)
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
                return await interaction.followup.send(
                    "⚠️ 현재 인원 구성과 팀 분리 조건으로 아레나 팀을 만들 수 없습니다.",
                    ephemeral=True
                )
            target = min(
                eligible_teams,
                key=lambda team: (team["total"], len(team["players"]))
            )
            target["players"].append(player)
            target["total"] += player["score"]
    
        teams.sort(key=lambda team: team["total"], reverse=True)
        totals = [team["total"] for team in teams]
        avg_total = round(sum(totals) / len(totals))
        gap = max(totals) - min(totals)
    
        embed = discord.Embed(
            title=f"🏟️ {q_num}번 큐 아레나(3x6) 팀 배정 결과",
            description=(
                f"총 18명을 **3명씩 6팀**으로 배정했습니다.\n"
                f"기준: 각 소환사의 **라인 중 최고 MMR** · 팀 평균 총점 **{avg_total}** · 최대 격차 **{gap}**"
            ),
            color=0xf39c12
        )
    
        for idx, team in enumerate(teams, 1):
            member_lines = [
                f"{p['user'].mention} · {get_public_mmr_rank(p['score'])} {get_tier_emoji(p.get('tier') or get_tier_name(p['score']), interaction.guild, gid)}"
                for p in sorted(team["players"], key=lambda item: item["score"], reverse=True)
            ]
            embed.add_field(
                name=f"아레나 팀 {idx} · 총점 {team['total']}",
                value="\n".join(member_lines),
                inline=False
            )
    
        bot.active_games.setdefault(gid, {})[q_num] = initialize_active_game_state(gid, q_num, {
            "mode": EVENT_MODE_KEY,
            "teams": [
                {
                    "name": f"아레나 팀 {idx}",
                    "team_no": idx,
                    "total": team["total"],
                    "players": [str(p["user"].id) for p in team["players"]]
                }
                for idx, team in enumerate(teams, 1)
            ]
        })
        _persist_active_game(gid, bot.active_games[gid][q_num])
    
        await send_or_edit_arena_reveal(interaction, gid, teams, embed)
    
        await create_and_move_team_voice_channels(
            interaction.guild,
            [
                (f"🏟️ 아레나 팀 {idx}", [p["user"] for p in team["players"]])
                for idx, team in enumerate(teams, 1)
            ],
            game_state=bot.active_games[gid][q_num],
        )
    
    async def internal_aram_lineup(interaction: discord.Interaction, q_num):
        gid = str(interaction.guild_id)
        q = bot.queues.get(gid, {}).get(q_num, [])
    
        if len(q) < ARAM_PLAYER_COUNT:
            msg = f"❌ 칼바람 나락 구성 실패: 인원 부족 ({len(q)}/{ARAM_PLAYER_COUNT})"
            if not interaction.response.is_done():
                return await interaction.response.send_message(msg)
            return await interaction.followup.send(msg)
    
        if not interaction.response.is_done():
            await interaction.response.defer()
    
        players = []
        for data in q[:ARAM_PLAYER_COUNT]:
            user = data[0]
            raw_info = bot.user_data.get(gid, {}).get(str(user.id), {'mmr': 0, 'lol_name': user.display_name})
            user_info = ensure_user_format(raw_info)
            peak_mmr = get_peak_mmr(user_info['mmr'])
            if peak_mmr <= 0:
                msg = format_mmr_eval_required_message(subject=user.display_name)
                if not interaction.response.is_done():
                    return await interaction.response.send_message(msg)
                return await interaction.followup.send(msg)
            tier = get_tier_name(peak_mmr)
            players.append({
                "user": user,
                "uid": str(user.id),
                "name": user_info.get('lol_name', user.display_name),
                "score": peak_mmr,
                "tier": tier,
            })
    
        uids = [p["uid"] for p in players]
        score_by_uid = {p["uid"]: p["score"] for p in players}
        best_combo, best_diff = choose_aram_blue_team(gid, uids, score_by_uid)
    
        if best_combo is None:
            return await interaction.followup.send(
                "⚠️ 현재 인원 구성과 팀 분리 조건으로 총력전 팀을 만들 수 없습니다.",
                ephemeral=True
            )
    
        blue_players = [p for p in players if p["uid"] in best_combo]
        red_players = [p for p in players if p["uid"] not in best_combo]
        blue_total = sum(p["score"] for p in blue_players)
        red_total = sum(p["score"] for p in red_players)
    
        bot.active_games.setdefault(gid, {})[q_num] = initialize_active_game_state(gid, q_num, {
            "mode": ARAM_MODE_KEY,
            "blue": [p["uid"] for p in blue_players],
            "red": [p["uid"] for p in red_players],
            "blue_total": blue_total,
            "red_total": red_total,
        })
        game_state = bot.active_games[gid][q_num]
        _persist_active_game(gid, game_state)
        await check_queue_lineup_titles(interaction, gid, q_num, q[:ARAM_PLAYER_COUNT])

        blue_channel_name, red_channel_name = get_classic_voice_channel_names(q_num)
        await create_and_move_team_voice_channels(
            interaction.guild,
            [
                (blue_channel_name, [p["user"] for p in blue_players]),
                (red_channel_name, [p["user"] for p in red_players]),
            ],
            game_state=game_state,
            include_waiting=True,
        )
    
        embed = discord.Embed(
            title="🎲 칼바람 나락 5v5 팀 배정 결과",
            description=(
                "최고 티어 MMR 기준으로 팀을 구성했습니다.\n"
                "이 모드는 **MMR과 일반 내전 전적에 영향을 주지 않습니다.**"
            ),
            color=0x1abc9c
        )
        embed.add_field(
            name=f"🔵 BLUE TEAM · 총점 {blue_total}",
            value="\n".join(f"{p['user'].mention} · {get_public_mmr_rank(p['score'])} {get_tier_emoji(p.get('tier') or get_tier_name(p['score']), interaction.guild, gid)}" for p in sorted(blue_players, key=lambda item: item["score"], reverse=True)),
            inline=False
        )
        embed.add_field(
            name=f"🔴 RED TEAM · 총점 {red_total}",
            value="\n".join(f"{p['user'].mention} · {get_public_mmr_rank(p['score'])} {get_tier_emoji(p.get('tier') or get_tier_name(p['score']), interaction.guild, gid)}" for p in sorted(red_players, key=lambda item: item["score"], reverse=True)),
            inline=False
        )
        embed.add_field(name="전력 차이", value=f"**{best_diff}점**", inline=False)
        await send_match_output(interaction, gid, embed=embed)
    
    def get_series_mode_name(game_state):
        if (game_state or {}).get("mode") == ARAM_LEAGUE_MODE_KEY:
            return ARAM_LEAGUE_MODE_NAME
        return LEAGUE_SERIES_MODE_NAME
    
    def get_series_queue_key(game_state):
        if (game_state or {}).get("mode") == ARAM_LEAGUE_MODE_KEY:
            return ARAM_LEAGUE_QUEUE_KEY
        return LEAGUE_SERIES_QUEUE_KEY
    
    def build_aram_league_teams(gid, q, team_count):
        _sync_runtime()
        player_count = int(team_count) * 5
        players = []
        for data in q[:player_count]:
            user, *_ = normalize_queue_entry(data)
            uid = str(user.id)
            raw_info = bot.user_data.get(gid, {}).get(uid, {'mmr': 0, 'lol_name': user.display_name})
            user_info = ensure_user_format(raw_info)
            score = int(get_peak_mmr(user_info.get('mmr', {})) or 0)
            if score <= 0:
                return None, format_mmr_eval_required_message(subject=user.display_name)
            players.append({
                "user": user, "uid": uid,
                "name": user_info.get('lol_name', user.display_name),
                "score": score, "tier": get_tier_name(score),
            })
        if len(players) != player_count:
            return None, f"⚠️ {ARAM_LEAGUE_MODE_NAME} 팀 구성 인원이 맞지 않습니다."
    
        avg_target = sum(p["score"] for p in players) / max(1, team_count)
        best = None
        best_metric = None
        rng = random.Random("aram-league:" + ":".join(sorted(p["uid"] for p in players)))
        for attempt in range(320):
            if attempt == 0:
                ordered = sorted(players, key=lambda p: (-p["score"], p["uid"]))
            else:
                ordered = sorted(players, key=lambda p: (-(p["score"] + rng.uniform(-180, 180)), p["uid"]))
            teams = [{"players": [], "total": 0} for _ in range(team_count)]
            failed = False
            for p in ordered:
                candidates = []
                for idx, team in enumerate(teams):
                    if len(team["players"]) >= 5:
                        continue
                    candidate_ids = [x["uid"] for x in team["players"]] + [p["uid"]]
                    if team_violates_separation(gid, candidate_ids):
                        continue
                    candidates.append((len(team["players"]), team["total"], rng.random(), idx))
                if not candidates:
                    failed = True
                    break
                _, _, _, idx = min(candidates)
                teams[idx]["players"].append(p)
                teams[idx]["total"] += p["score"]
            if failed or any(len(t["players"]) != 5 for t in teams):
                continue
            totals = [t["total"] for t in teams]
            metric = (max(totals) - min(totals), sum(abs(x - avg_target) for x in totals))
            if best_metric is None or metric < best_metric:
                best_metric = metric
                best = teams
        if best is None:
            return None, f"⚠️ 현재 참가자 구성과 팀 분리 조건으로 {ARAM_LEAGUE_MODE_NAME} 팀을 만들 수 없습니다."
    
        result = []
        for idx, team in enumerate(sorted(best, key=lambda t: -t["total"]), 1):
            player_ids = [p["uid"] for p in team["players"]]
            result.append({
                "name": f"{idx}팀",
                "team_no": idx,
                "total": int(team["total"]),
                "display_total": int(team["total"]),
                "player_ids": player_ids,
                "players_list": list(team["players"]),
                "roles": {},
                "player_names": {p["uid"]: p["name"] for p in team["players"]},
                "player_scores": {p["uid"]: p["score"] for p in team["players"]},
            })
        return result, None
    
    def get_league_team_gap_hard_limit(team_count, override=None):
        if override is not None:
            return min(600, max(0, int(override)))
        return LEAGUE_TEAM_GAP_LIMIT_BY_COUNT.get(int(team_count), 1000)
    
    def get_league_team_gap_limit_attempts(team_count, override=None):
        base_limit = get_league_team_gap_hard_limit(team_count, override)
        limits = [base_limit]
        if override is None:
            limits.extend(limit for limit in LEAGUE_TEAM_GAP_FALLBACK_LIMITS if limit > base_limit)
        return list(dict.fromkeys(min(600, int(limit)) for limit in limits))
    
    def build_league_teams(
        gid,
        q,
        team_count=LEAGUE_TEAM_COUNT,
        mode_name=LEAGUE_MODE_NAME,
        team_gap_soft_limit=LEAGUE_TEAM_GAP_SOFT_LIMIT,
        lane_gap_soft_limit=LEAGUE_LANE_GAP_SOFT_LIMIT,
        lane_gap_heavy_limit=LEAGUE_LANE_GAP_HEAVY_LIMIT,
        team_gap_hard_limit=None,
    ):
        _sync_runtime()
        players = []
        player_count = int(team_count) * len(ROLES)
        league_queue_scores = []
        for data in q[:player_count]:
            user, _, pref1, pref2, pref3 = normalize_queue_entry(data)
            raw_info = bot.user_data.get(gid, {}).get(str(user.id), {})
            user_info = ensure_user_format(raw_info)
            league_queue_scores.append(get_queue_display_mmr(user_info, pref1, pref2, pref3))
        league_queue_avg_mmr = round(sum(league_queue_scores) / len(league_queue_scores)) if league_queue_scores else 0
        for data in q[:player_count]:
            user, _, pref1, pref2, pref3 = normalize_queue_entry(data)
            uid = str(user.id)
            raw_info = bot.user_data.get(gid, {}).get(uid, {'mmr': 0, 'lol_name': user.display_name})
            user_info = ensure_user_format(raw_info)
            requested = get_requested_roles(pref1, pref2, pref3)
            option_override = data[5] if len(data) > 5 and isinstance(data[5], list) else None
            options = option_override if option_override else (requested if requested else get_playable_roles(user_info))
            options = [role for role in options if role in ROLES]
            if not options:
                return None, format_mmr_eval_required_message(requested, user.display_name)
            players.append({
                "user": user,
                "uid": uid,
                "name": user_info.get('lol_name', user.display_name),
                "mmr": user_info['mmr'],
                "weighted_mmr": {
                    role: calculate_lineup_weighted_mmr(
                        user_info, role, queue_avg_mmr=league_queue_avg_mmr, queue_scores=league_queue_scores
                    )
                    for role in ROLES
                },
                "options": options,
            })
    
        players.sort(key=lambda item: (len(item["options"]), -max(item["weighted_mmr"].get(r, 0) for r in item["options"])))
        team_gap_limit_attempts = get_league_team_gap_limit_attempts(team_count, team_gap_hard_limit)
        role_counts = {role: 0 for role in ROLES}
        assigned = {}
        assignment_candidates = []
        node_count = 0
        node_limit = 30000
        candidate_limit = 8 if team_count <= 5 else 16
    
        def build_role_spread_metric(assignment):
            spreads = []
            for role in ROLES:
                scores = [
                    player["mmr"].get(role, 0)
                    for player in players
                    if assignment.get(player["uid"]) == role
                ]
                if len(scores) != team_count:
                    return (float("inf"), float("inf"))
                spreads.append(max(scores) - min(scores))
            return max(spreads), sum(spreads)
    
        def add_assignment_candidate():
            metric = build_role_spread_metric(assigned)
            assignment_candidates.append((metric, dict(assigned)))
            assignment_candidates.sort(key=lambda item: item[0])
            if len(assignment_candidates) > candidate_limit:
                assignment_candidates.pop()
    
        def add_fast_assignment_candidates():
            seen = set()
            for offset in range(len(ROLES)):
                for high_first in (True, False):
                    role_counts.update({role: 0 for role in ROLES})
                    assigned.clear()
                    ordered_players = sorted(
                        players,
                        key=lambda item: (
                            len(item["options"]),
                            -max(item["weighted_mmr"].get(role, 0) for role in item["options"]) if high_first else max(item["weighted_mmr"].get(role, 0) for role in item["options"]),
                            item["uid"],
                        )
                    )
                    failed = False
                    for idx, player in enumerate(ordered_players):
                        remaining_players = ordered_players[idx + 1:]
                        role_order = sorted(
                            player["options"],
                            key=lambda role: (
                                role_counts[role],
                                -player["weighted_mmr"].get(role, 0),
                                (ROLES.index(role) - offset) % len(ROLES),
                            )
                        )
                        chosen_role = None
                        for role in role_order:
                            if role_counts[role] >= team_count:
                                continue
                            possible = True
                            for check_role in ROLES:
                                future_candidates = sum(
                                    1
                                    for future_player in remaining_players
                                    if check_role in future_player["options"]
                                )
                                added = 1 if check_role == role else 0
                                if role_counts[check_role] + added + future_candidates < team_count:
                                    possible = False
                                    break
                            if possible:
                                chosen_role = role
                                break
                        if not chosen_role:
                            failed = True
                            break
                        assigned[player["uid"]] = chosen_role
                        role_counts[chosen_role] += 1
                    if failed or any(role_counts[role] != team_count for role in ROLES):
                        continue
                    key = tuple(sorted(assigned.items()))
                    if key in seen:
                        continue
                    seen.add(key)
                    add_assignment_candidate()
                    if len(assignment_candidates) >= candidate_limit:
                        return
    
        def search_role_assignment(idx):
            nonlocal node_count
            node_count += 1
            if node_count > node_limit:
                return
            if idx == len(players):
                if any(role_counts[role] != team_count for role in ROLES):
                    return
                add_assignment_candidate()
                return
    
            remaining = len(players) - idx - 1
            player = players[idx]
            role_order = sorted(player["options"], key=lambda role: (role_counts[role], -player["weighted_mmr"].get(role, 0)))
            for role in role_order:
                if role_counts[role] >= team_count:
                    continue
                if role_counts[role] + 1 + remaining < team_count:
                    continue
                impossible = False
                for check_role in ROLES:
                    future_candidates = sum(
                        1 for future_player in players[idx + 1:]
                        if check_role in future_player["options"]
                    )
                    added = 1 if check_role == role else 0
                    if role_counts[check_role] + added + future_candidates < team_count:
                        impossible = True
                        break
                if impossible:
                    continue
                role_counts[role] += 1
                assigned[player["uid"]] = role
                search_role_assignment(idx + 1)
                if len(assignment_candidates) >= candidate_limit:
                    return
                assigned.pop(player["uid"], None)
                role_counts[role] -= 1
    
        if team_count > 5:
            add_fast_assignment_candidates()
        if not assignment_candidates:
            search_role_assignment(0)
        if not assignment_candidates:
            return None, f"⚠️ 현재 신청자의 지망/가능 라인 구성으로는 각 라인 {team_count}명씩 {mode_name} 팀을 만들 수 없습니다."
    
        best_teams = None
        best_score = None
        used_team_gap_limit = None
        for current_gap_limit in team_gap_limit_attempts:
            best_teams = None
            best_score = None
            for spread_metric, candidate_assignment in assignment_candidates:
                buckets = {role: [] for role in ROLES}
                for player in players:
                    role = candidate_assignment[player["uid"]]
                    score = int(player["mmr"].get(role, 0) or 0)
                    weighted_score = int(player["weighted_mmr"].get(role, 0) or 0)
                    buckets[role].append({**player, "role": role, "score": score, "weighted_score": weighted_score})
                teams, team_gap = balance_league_role_buckets(
                    gid,
                    buckets,
                    team_count=team_count,
                    mode_name=mode_name,
                    team_gap_soft_limit=team_gap_soft_limit,
                    lane_gap_soft_limit=lane_gap_soft_limit,
                    lane_gap_heavy_limit=lane_gap_heavy_limit,
                    team_gap_hard_limit=current_gap_limit,
                )
                if not teams:
                    continue
                score = (teams[0].get("_balance_score", (float("inf"),)), spread_metric[0], spread_metric[1], team_gap)
                if best_score is None or score < best_score:
                    best_score = score
                    best_teams = teams
                    used_team_gap_limit = current_gap_limit
            if best_teams:
                break
    
        if not best_teams:
            return None, f"⚠️ 현재 신청자/라인 구성으로는 팀 총점 격차 {team_gap_limit_attempts[-1]}점 이내 {mode_name} 팀을 만들 수 없습니다."
        for team in best_teams:
            team["_team_gap_limit_used"] = used_team_gap_limit
        return best_teams, None
    
    class LeagueSimulationUser:
        def __init__(self, uid, display_name):
            self.id = int(uid)
            self.display_name = display_name
    
        @property
        def mention(self):
            return discord.utils.escape_markdown(self.display_name)
    
    def balance_league_role_buckets(
        gid,
        role_buckets,
        team_count=LEAGUE_TEAM_COUNT,
        mode_name=LEAGUE_MODE_NAME,
        team_gap_soft_limit=LEAGUE_TEAM_GAP_SOFT_LIMIT,
        lane_gap_soft_limit=LEAGUE_LANE_GAP_SOFT_LIMIT,
        lane_gap_heavy_limit=LEAGUE_LANE_GAP_HEAVY_LIMIT,
        team_gap_hard_limit=None,
    ):
        beam_width = 350 if team_count <= 5 else 60
        team_gap_hard_limit = get_league_team_gap_hard_limit(team_count, team_gap_hard_limit)
        states = [(
            [{"players": {}, "total": 0, "display_total": 0} for _ in range(team_count)],
            (0, 0, 0)
        )]
        tier_pool = [
            player
            for candidates in role_buckets.values()
            for player in candidates
        ]
        tier_pool.sort(key=lambda item: int(item.get("score", 0) or 0), reverse=True)
    
        def build_percentile_tier(percent):
            if not tier_pool:
                return set(), {}, 0
            tier_count = max(1, (len(tier_pool) * percent + 99) // 100)
            selected = tier_pool[:tier_count]
            return (
                {player["uid"] for player in selected},
                {player["uid"]: int(player.get("score", 0) or 0) for player in selected},
                max(1, (tier_count + team_count - 1) // team_count),
            )
    
        high_tier_uids, high_tier_scores, high_tier_target_per_team = build_percentile_tier(LEAGUE_HIGH_TIER_PERCENT)
        elite_tier_uids, elite_tier_scores, elite_tier_target_per_team = build_percentile_tier(LEAGUE_ELITE_TIER_PERCENT)
    
        def league_team_lane_gap(left_team, right_team):
            gaps = [
                abs(left_team["players"][role]["score"] - right_team["players"][role]["score"])
                for role in ROLES
                if role in left_team["players"] and role in right_team["players"]
            ]
            return (max(gaps), sum(gaps)) if gaps else (float("inf"), float("inf"))
    
        def league_lane_gap_penalty_from_gaps(gaps):
            soft = sum(max(0, gap - lane_gap_soft_limit) for gap in gaps)
            heavy = sum(max(0, gap - lane_gap_heavy_limit) for gap in gaps)
            return soft + (heavy * 2)
    
        def league_percentile_tier_stack_penalty(
            teams,
            tier_uids,
            tier_scores,
            target_per_team,
            count_penalty,
            spread_penalty,
            impact_stack_penalty,
            double_impact_penalty,
        ):
            if not tier_uids:
                return 0
            tier_counts = []
            tier_score_totals = []
            penalty = 0
            for team in teams:
                players = team.get("players", {}) or {}
                tier_players = [
                    player
                    for player in players.values()
                    if player.get("uid") in tier_uids
                ]
                tier_count = len(tier_players)
                tier_counts.append(tier_count)
                tier_score_totals.append(sum(tier_scores.get(player.get("uid"), 0) for player in tier_players))
                impact_count = sum(
                    1
                    for role in LEAGUE_IMPACT_HIGH_ROLES
                    if players.get(role, {}).get("uid") in tier_uids
                )
                if target_per_team and tier_count > target_per_team:
                    penalty += (tier_count - target_per_team) * count_penalty
                if tier_count >= 2 and impact_count:
                    penalty += impact_count * (tier_count - 1) * impact_stack_penalty
                if impact_count >= 2:
                    penalty += (impact_count - 1) * double_impact_penalty
            if tier_counts:
                penalty += (max(tier_counts) - min(tier_counts)) * spread_penalty
            if tier_score_totals:
                penalty += int((max(tier_score_totals) - min(tier_score_totals)) * LEAGUE_HIGH_TIER_SCORE_SPREAD_WEIGHT)
            return penalty
    
        def league_high_tier_stack_penalty(teams):
            penalty = league_percentile_tier_stack_penalty(
                teams,
                high_tier_uids,
                high_tier_scores,
                high_tier_target_per_team,
                LEAGUE_HIGH_TIER_COUNT_PENALTY,
                LEAGUE_HIGH_TIER_SPREAD_PENALTY,
                LEAGUE_IMPACT_HIGH_STACK_PENALTY,
                LEAGUE_DOUBLE_IMPACT_HIGH_PENALTY,
            )
            penalty += league_percentile_tier_stack_penalty(
                teams,
                elite_tier_uids,
                elite_tier_scores,
                elite_tier_target_per_team,
                LEAGUE_ELITE_TIER_COUNT_PENALTY,
                LEAGUE_ELITE_TIER_SPREAD_PENALTY,
                LEAGUE_IMPACT_HIGH_STACK_PENALTY * 2,
                LEAGUE_DOUBLE_IMPACT_HIGH_PENALTY * 2,
            )
            return penalty
    
        def league_elite_absence_compensation_penalty(teams):
            if not elite_tier_uids or not teams:
                return 0
            totals = [int(team.get("display_total", team.get("total", 0)) or 0) for team in teams]
            avg_total = sum(totals) / len(totals) if totals else 0
            impact_scores = [
                int(team.get("players", {}).get(role, {}).get("score", 0) or 0)
                for team in teams
                for role in LEAGUE_IMPACT_HIGH_ROLES
                if role in team.get("players", {})
            ]
            avg_impact = sum(impact_scores) / len(impact_scores) if impact_scores else 0
            empty_teams = []
            penalty = 0
            for team in teams:
                players = team.get("players", {}) or {}
                elite_count = sum(1 for player in players.values() if player.get("uid") in elite_tier_uids)
                if elite_count:
                    continue
                empty_teams.append(team)
                team_total = int(team.get("display_total", team.get("total", 0)) or 0)
                if team_total < avg_total:
                    penalty += int((avg_total - team_total) * LEAGUE_ELITE_EMPTY_LOW_TOTAL_WEIGHT)
                for role in LEAGUE_IMPACT_HIGH_ROLES:
                    role_score = int(players.get(role, {}).get("score", 0) or 0)
                    low_gap = int(avg_impact - role_score)
                    if low_gap > LEAGUE_ELITE_EMPTY_IMPACT_FLOOR_GAP:
                        penalty += (low_gap - LEAGUE_ELITE_EMPTY_IMPACT_FLOOR_GAP) * LEAGUE_ELITE_EMPTY_IMPACT_LOW_WEIGHT
            unavoidable_empty_count = max(0, team_count - len(elite_tier_uids))
            extra_empty_count = max(0, len(empty_teams) - unavoidable_empty_count)
            penalty += extra_empty_count * LEAGUE_ELITE_EMPTY_TEAM_PENALTY
            return penalty
    
        def league_tournament_future_gap_score(teams):
            if len(teams) < team_count or any(len(team["players"]) < len(ROLES) for team in teams):
                return (float("inf"), float("inf"), float("inf"), float("inf"))
            worst_lane_gap = 0
            total_pair_lane_gap = 0
            total_pair_team_gap = 0
            lane_gap_penalty = 0
            for left_team, right_team in itertools.combinations(teams, 2):
                gaps = [
                    abs(left_team["players"][role]["score"] - right_team["players"][role]["score"])
                    for role in ROLES
                ]
                max_gap = max(gaps)
                sum_gap = sum(gaps)
                worst_lane_gap = max(worst_lane_gap, max_gap)
                total_pair_lane_gap += sum_gap
                total_pair_team_gap += abs(left_team["total"] - right_team["total"])
                lane_gap_penalty += league_lane_gap_penalty_from_gaps(gaps)
            return worst_lane_gap, total_pair_lane_gap, lane_gap_penalty, total_pair_team_gap
    
        def team_score(teams):
            totals = [team.get("display_total", team["total"]) for team in teams]
            avg = sum(totals) / len(totals)
            team_gap = max(totals) - min(totals)
            team_gap_over_soft_limit = max(0, team_gap - team_gap_soft_limit)
            future_max_lane_gap, future_lane_gap_sum, future_lane_gap_penalty, future_team_gap_sum = league_tournament_future_gap_score(teams)
            high_tier_stack_penalty = league_high_tier_stack_penalty(teams)
            elite_absence_penalty = league_elite_absence_compensation_penalty(teams)
            return (
                high_tier_stack_penalty,
                elite_absence_penalty,
                team_gap_over_soft_limit,
                team_gap,
                future_max_lane_gap,
                future_lane_gap_penalty,
                future_lane_gap_sum,
                future_team_gap_sum,
                sum(abs(total - avg) for total in totals),
                max(totals),
            )
    
        for role in ROLES:
            candidates = role_buckets.get(role, [])
            if len(candidates) != team_count:
                return None, float("inf")
            role_permutations = []
            if team_count <= 5:
                role_permutations = list(itertools.permutations(candidates, team_count))
            else:
                sorted_candidates = sorted(candidates, key=lambda item: int(item.get("score", 0) or 0), reverse=True)
                for offset in range(team_count):
                    role_permutations.append(tuple(sorted_candidates[offset:] + sorted_candidates[:offset]))
                sample_limit = 900 if team_count <= 5 else 90
                seen = {tuple(item["uid"] for item in perm) for perm in role_permutations}
                attempts = 0
                while len(role_permutations) < sample_limit and attempts < sample_limit * 4:
                    attempts += 1
                    perm = tuple(random.sample(candidates, team_count))
                    key = tuple(item["uid"] for item in perm)
                    if key in seen:
                        continue
                    seen.add(key)
                    role_permutations.append(perm)
            next_states = []
            for teams, _ in states:
                for perm in role_permutations:
                    new_teams = [
                        {
                            "players": dict(team["players"]),
                            "total": team["total"],
                            "display_total": team.get("display_total", 0),
                        }
                        for team in teams
                    ]
                    for idx, player in enumerate(perm):
                        new_teams[idx]["players"][role] = player
                        new_teams[idx]["total"] += int(player.get("weighted_score", player["score"]) or 0)
                        new_teams[idx]["display_total"] += int(player["score"] or 0)
                    if any(
                        team_violates_separation(
                            gid,
                            [item["uid"] for item in team["players"].values()]
                        )
                        for team in new_teams
                    ):
                        continue
                    if all(len(team["players"]) == len(ROLES) for team in new_teams):
                        display_totals = [team.get("display_total", team["total"]) for team in new_teams]
                        if max(display_totals) - min(display_totals) > team_gap_hard_limit:
                            continue
                    next_states.append((new_teams, team_score(new_teams)))
            next_states.sort(key=lambda item: item[1])
            states = next_states[:beam_width]
            if not states:
                return None, float("inf")
    
        complete_states = []
        for teams, score in states:
            display_totals = [team.get("display_total", team["total"]) for team in teams]
            if max(display_totals) - min(display_totals) <= team_gap_hard_limit:
                complete_states.append((teams, score))
        if not complete_states:
            return None, float("inf")
    
        best_teams, best_score = min(complete_states, key=lambda item: item[1])
        best_gap = max(team.get("display_total", team["total"]) for team in best_teams) - min(team.get("display_total", team["total"]) for team in best_teams)
        if best_teams:
            for idx, team in enumerate(best_teams, 1):
                team["team_no"] = idx
                team["name"] = f"{mode_name} {idx}팀"
                team["player_ids"] = [team["players"][role]["uid"] for role in ROLES]
                team["_balance_score"] = best_score
        return best_teams, best_gap
    
    def build_league_matchups(teams):
        teams_by_no = {team["team_no"]: team for team in teams}
        team_nos = [team["team_no"] for team in teams]
        pairings = [
            [[team_nos[0], team_nos[1]], [team_nos[2], team_nos[3]]],
            [[team_nos[0], team_nos[2]], [team_nos[1], team_nos[3]]],
            [[team_nos[0], team_nos[3]], [team_nos[1], team_nos[2]]],
        ]
    
        def pair_gap(left_team, right_team):
            lane_gaps = [
                abs(left_team["players"][role]["score"] - right_team["players"][role]["score"])
                for role in ROLES
            ]
            return max(lane_gaps), sum(lane_gaps), abs(left_team["total"] - right_team["total"])
    
        def lane_gap_penalty(left_team, right_team):
            lane_gaps = [
                abs(left_team["players"][role]["score"] - right_team["players"][role]["score"])
                for role in ROLES
            ]
            soft = sum(max(0, gap - LEAGUE_LANE_GAP_SOFT_LIMIT) for gap in lane_gaps)
            heavy = sum(max(0, gap - LEAGUE_LANE_GAP_HEAVY_LIMIT) for gap in lane_gaps)
            return soft + (heavy * 2)
    
        def lane_gap_metric(pairing):
            semifinal_max_lane_gap = 0
            semifinal_total_lane_gap = 0
            semifinal_total_team_gap = 0
            semifinal_lane_penalty = 0
            semifinal_max_team_gap = 0
            for left_no, right_no in pairing:
                left_team = teams_by_no[left_no]
                right_team = teams_by_no[right_no]
                pair_max_gap, pair_sum_gap, pair_team_gap = pair_gap(left_team, right_team)
                semifinal_max_lane_gap = max(semifinal_max_lane_gap, pair_max_gap)
                semifinal_total_lane_gap += pair_sum_gap
                semifinal_total_team_gap += pair_team_gap
                semifinal_max_team_gap = max(semifinal_max_team_gap, pair_team_gap)
                semifinal_lane_penalty += lane_gap_penalty(left_team, right_team)
    
            final_cases = [
                (pairing[0][0], pairing[1][0]),
                (pairing[0][0], pairing[1][1]),
                (pairing[0][1], pairing[1][0]),
                (pairing[0][1], pairing[1][1]),
            ]
            final_max_lane_gap = 0
            final_total_lane_gap = 0
            final_total_team_gap = 0
            final_max_team_gap = 0
            final_lane_penalty = 0
            for left_no, right_no in final_cases:
                left_team = teams_by_no[left_no]
                right_team = teams_by_no[right_no]
                pair_max_gap, pair_sum_gap, pair_team_gap = pair_gap(left_team, right_team)
                final_max_lane_gap = max(final_max_lane_gap, pair_max_gap)
                final_total_lane_gap += pair_sum_gap
                final_total_team_gap += pair_team_gap
                final_max_team_gap = max(final_max_team_gap, pair_team_gap)
                final_lane_penalty += lane_gap_penalty(left_team, right_team)
    
            worst_team_gap = max(final_max_team_gap, semifinal_max_team_gap)
            team_gap_over_soft_limit = max(0, worst_team_gap - LEAGUE_TEAM_GAP_SOFT_LIMIT)
            combined_max_lane_gap = max(semifinal_max_lane_gap, final_max_lane_gap)
            combined_lane_penalty = semifinal_lane_penalty + final_lane_penalty
            combined_total_lane_gap = semifinal_total_lane_gap + final_total_lane_gap
    
            return (
                semifinal_max_lane_gap,
                semifinal_lane_penalty,
                semifinal_total_lane_gap,
                final_max_lane_gap,
                final_lane_penalty,
                final_total_lane_gap,
                combined_max_lane_gap,
                combined_lane_penalty,
                combined_total_lane_gap,
                team_gap_over_soft_limit,
                worst_team_gap,
                semifinal_total_team_gap,
                final_total_team_gap,
            )
    
        best_score = None
        best_pairings = []
        for pairing in pairings:
            score = lane_gap_metric(pairing)
            if best_score is None or score < best_score:
                best_score = score
                best_pairings = [pairing]
            elif score == best_score:
                best_pairings.append(pairing)
    
        matchups = [list(pair) for pair in random.choice(best_pairings)]
        random.shuffle(matchups)
        for matchup in matchups:
            if random.random() < 0.5:
                matchup.reverse()
        return matchups
    
    def build_league_4team_bracket_diagram(matchups, matches=None):
        matches = matches or {}
        left_a, left_b = matchups[0]
        right_a, right_b = matchups[1]
        semi_1_winner = matches.get("1", {}).get("winner")
        semi_2_winner = matches.get("2", {}).get("winner")
        final_winner = matches.get("3", {}).get("winner")
        final_left = f"{semi_1_winner}팀" if semi_1_winner else "M1 승자"
        final_right = f"{semi_2_winner}팀" if semi_2_winner else "M2 승자"
        champion = f"{final_winner}팀" if final_winner else "M3 승자"
        return "\n".join([
            "🏆 결승",
            f"M3  {final_left} vs {final_right}  → {champion}",
            "",
            "🔺 4강",
            f"M1  {left_a}팀 vs {left_b}팀",
            f"M2  {right_a}팀 vs {right_b}팀",
        ])
    
    def build_existing_league_bracket_embed(guild, gid, game_state, *, title_suffix="진행 중 대진표"):
        matches = game_state.get("matches", {}) or {}
        matchups = [
            matches.get("1", {}).get("team_nos", []),
            matches.get("2", {}).get("team_nos", []),
        ]
        if len(matchups[0]) != 2 or len(matchups[1]) != 2:
            bracket_text = "대진표 정보가 아직 완성되지 않았습니다."
        else:
            bracket_text = build_league_4team_bracket_diagram(matchups, matches)
    
        embed = discord.Embed(
            title=f"🏆 {LEAGUE_MODE_NAME} {game_state.get('round_no', '?')}회차 {title_suffix}",
            description=f"```text\n{bracket_text}\n```",
            color=0x9b59b6,
        )
        teams_by_no = {int(team.get("team_no")): team for team in game_state.get("teams", []) if team.get("team_no")}
        for match_no in ("1", "2", "3"):
            match = matches.get(match_no, {})
            team_nos = match.get("team_nos", []) or []
            if len(team_nos) == 2:
                left = format_league_team_name(teams_by_no.get(int(team_nos[0]), {"team_no": team_nos[0]}))
                right = format_league_team_name(teams_by_no.get(int(team_nos[1]), {"team_no": team_nos[1]}))
                suffix = ""
                if match.get("winner"):
                    suffix = f" → ✅ {format_league_team_name(teams_by_no.get(int(match['winner']), {'team_no': match['winner']}))} 승리"
                embed.add_field(name=f"매치 {match_no}", value=f"**{left} vs {right}**{suffix}", inline=False)
        return embed
    
    def is_power_of_two(value):
        return value > 0 and (value & (value - 1)) == 0
    
    def highest_power_of_two_below(value):
        power = 1
        while power * 2 < value:
            power *= 2
        return power
    
    def build_series_round_name(slot_count):
        return "결승" if slot_count <= 2 else f"{slot_count}강"
    
    def build_league_series_bracket(team_count, *, third_place=False):
        team_nos = list(range(1, team_count + 1))
        random.shuffle(team_nos)
        matches = {}
        match_order = []
        next_match_no = 1
    
        def add_match(round_index, round_name, slots, **extra):
            nonlocal next_match_no
            match_id = str(next_match_no)
            next_match_no += 1
            matches[match_id] = {
                "match_no": int(match_id),
                "round_index": round_index,
                "round_name": round_name,
                "slots": slots,
                "winner": None,
                **extra,
            }
            match_order.append(match_id)
            return match_id
    
        if is_power_of_two(team_count):
            participants = [{"team_no": no} for no in team_nos]
            round_size = team_count
        else:
            bracket_size = highest_power_of_two_below(team_count)
            play_in_count = team_count - bracket_size
            bye_count = bracket_size - play_in_count
            bye_participants = [{"team_no": no} for no in team_nos[:bye_count]]
            play_in_teams = team_nos[bye_count:]
            play_in_winners = []
            for idx in range(play_in_count):
                left = play_in_teams[idx * 2]
                right = play_in_teams[idx * 2 + 1]
                match_id = add_match(0, "예비 라운드", [{"team_no": left}, {"team_no": right}])
                play_in_winners.append({"from": match_id})
            participants = bye_participants + play_in_winners
            random.shuffle(participants)
            round_size = bracket_size
    
        round_index = 1
        while len(participants) > 1:
            round_name = build_series_round_name(round_size)
            next_participants = []
            for idx in range(0, len(participants), 2):
                match_id = add_match(round_index, round_name, [participants[idx], participants[idx + 1]])
                next_participants.append({"from": match_id})
            participants = next_participants
            round_size //= 2
            round_index += 1
    
        if third_place and team_count >= 4 and match_order:
            final_match_id = next((mid for mid in reversed(match_order) if matches.get(mid, {}).get("round_name") == "결승"), None)
            final_match = matches.get(str(final_match_id), {}) if final_match_id else {}
            semifinal_sources = [
                str(slot.get("from"))
                for slot in final_match.get("slots", [])
                if slot.get("from")
            ]
            if len(semifinal_sources) == 2:
                add_match(
                    int(final_match.get("round_index", 0) or 0),
                    "3/4위전",
                    [{"loser_from": semifinal_sources[0]}, {"loser_from": semifinal_sources[1]}],
                    placement="third_place",
                )
    
        return {"matches": matches, "match_order": match_order}
    
    def resolve_series_slot(slot, matches):
        if "team_no" in slot:
            return slot.get("team_no")
        if "loser_from" in slot:
            source = matches.get(str(slot.get("loser_from")), {})
            winner = source.get("winner")
            source_team_nos = get_series_match_team_nos(source, matches) if source else []
            if not winner or len(source_team_nos) != 2:
                return None
            return next((team_no for team_no in source_team_nos if int(team_no) != int(winner)), None)
        source = matches.get(str(slot.get("from")), {})
        return source.get("winner")
    
    def get_series_match_team_nos(match, matches):
        return [resolve_series_slot(slot, matches) for slot in match.get("slots", [])]
    
    def is_series_match_playable(match, matches):
        return not match.get("winner") and all(get_series_match_team_nos(match, matches))
    
    def format_series_slot_label(slot, matches, teams_by_no):
        team_no = resolve_series_slot(slot, matches)
        if team_no:
            return format_league_team_name(teams_by_no.get(team_no, {"team_no": team_no}))
        source = slot.get("from")
        if source:
            source_match = matches.get(str(source), {})
            if source_match.get("winner"):
                winner_no = source_match.get("winner")
                return format_league_team_name(teams_by_no.get(winner_no, {"team_no": winner_no}))
            return f"매치 {source} 승자"
        loser_source = slot.get("loser_from")
        if loser_source:
            loser_no = resolve_series_slot(slot, matches)
            if loser_no:
                return format_league_team_name(teams_by_no.get(loser_no, {"team_no": loser_no}))
            return f"매치 {loser_source} 패자"
        return "대기"
    
    def format_series_compact_slot_label(slot, matches, teams_by_no):
        team_no = resolve_series_slot(slot, matches)
        if team_no:
            return f"{team_no}팀"
        source = slot.get("from")
        if source:
            source_match = matches.get(str(source), {})
            if source_match.get("winner"):
                return f"{source_match.get('winner')}팀"
            return f"M{source} 승자"
        loser_source = slot.get("loser_from")
        if loser_source:
            loser_no = resolve_series_slot(slot, matches)
            if loser_no:
                return f"{loser_no}팀"
            return f"M{loser_source} 패자"
        return "대기"
    
    def format_series_compact_match_label(match, matches, teams_by_no):
        if match.get("winner"):
            return f"{match.get('winner')}팀"
        return f"M{match.get('match_no')} 승자"
    
    def center_text(text, width):
        text = str(text or "")
        if len(text) >= width:
            return text[:width]
        left = (width - len(text)) // 2
        return " " * left + text + " " * (width - len(text) - left)
    
    def build_league_series_bracket_diagram(game_state):
        teams_by_no = {team.get("team_no"): team for team in game_state.get("teams", [])}
        matches = game_state.get("matches", {}) or {}
        rounds = defaultdict(list)
        placement_matches = []
        for match_id in game_state.get("match_order", []):
            match = matches.get(str(match_id), {})
            if match.get("placement") == "third_place":
                placement_matches.append(match)
                continue
            rounds[int(match.get("round_index", 0) or 0)].append(match)
    
        main_round_indexes = sorted(idx for idx in rounds if idx > 0)
        if not main_round_indexes:
            play_in_lines = []
            for match in rounds.get(0, []):
                slots = match.get("slots", [{}, {}])
                left = format_series_compact_slot_label(slots[0], matches, teams_by_no)
                right = format_series_compact_slot_label(slots[1], matches, teams_by_no)
                play_in_lines.append(f"M{match['match_no']}  🔵 {left} vs {right} 🔴")
            return "[예비 라운드]\n" + "\n".join(play_in_lines)
    
        def match_line(match):
            slots = match.get("slots", [{}, {}])
            left = format_series_compact_slot_label(slots[0], matches, teams_by_no)
            right = format_series_compact_slot_label(slots[1], matches, teams_by_no)
            winner = match.get("winner")
            suffix = f"  → {winner}팀" if winner else ""
            return f"M{match['match_no']}  🔵 {left} vs {right} 🔴{suffix}"
    
        lines = []
        for idx in reversed(main_round_indexes):
            round_matches = rounds.get(idx, [])
            round_name = (round_matches[0].get("round_name") if round_matches else "라운드") or "라운드"
            icon = "🏆" if round_name == "결승" else ("🔺" if "강" in round_name else "⚔️")
            lines.append(f"{icon} {round_name}")
            lines.extend(match_line(match) for match in round_matches)
            lines.append("")
            if round_name == "결승" and placement_matches:
                lines.append("🥉 3/4위전")
                lines.extend(match_line(match) for match in placement_matches)
                lines.append("")
    
        play_in_matches = rounds.get(0, [])
        if play_in_matches:
            lines.append("⚔️ 예비 라운드")
            lines.extend(match_line(match) for match in play_in_matches)
            lines.append("")
    
        return "\n".join(lines).strip()
    
    def build_league_series_embed(guild, gid, game_state, *, title_suffix="대진표"):
        teams_by_no = {team.get("team_no"): team for team in game_state.get("teams", [])}
        series_name = get_series_mode_name(game_state)
        matches = game_state.get("matches", {})
        bracket_diagram = build_league_series_bracket_diagram(game_state)
        diagram_text = f"\n```text\n{bracket_diagram}\n```" if bracket_diagram else ""
        embed = discord.Embed(
            title=f"🏆 {series_name} {game_state.get('round_no', '?')}회차 {title_suffix}",
            description=(
                f"팀 **{len(teams_by_no)}개** · 참가 **{len(teams_by_no) * 5}명**\n"
                f"각 매치는 `/승리 대상:{series_name} 매치번호:[번호] 승리팀:[팀]` 으로 입력합니다."
                f"{diagram_text}"
            ),
            color=0x9b59b6,
        )
        current_round = None
        lines = []
        for match_id in game_state.get("match_order", []):
            match = matches.get(str(match_id), {})
            round_name = match.get("round_name", "라운드")
            if current_round and round_name != current_round:
                embed.add_field(name=current_round, value="\n".join(lines) or "기록 없음", inline=False)
                lines = []
            current_round = round_name
            team_nos = get_series_match_team_nos(match, matches)
            labels = []
            for idx, slot in enumerate(match.get("slots", [])):
                team_no = team_nos[idx] if idx < len(team_nos) else None
                if team_no:
                    labels.append(format_league_team_name(teams_by_no.get(team_no, {"team_no": team_no})))
                else:
                    labels.append(format_series_slot_label(slot, matches, teams_by_no))
            match_line = f"`M{match_id}` 🔵 **{' vs '.join(labels)}** 🔴"
            if match.get("winner"):
                winner_label = format_league_team_name(teams_by_no.get(match.get('winner'), {'team_no': match.get('winner')}))
                match_line += f" → ✅ {winner_label} 승리"
            elif not is_series_match_playable(match, matches):
                match_line += " → 대기"
            else:
                match_line += ""
            lines.append(match_line)
        if current_round:
            embed.add_field(name=current_round, value="\n".join(lines) or "기록 없음", inline=False)
        if game_state.get("simulation"):
            source_text = "서버 실제 유저 랜덤 샘플" if not game_state.get("sim_used_dummy") else "샘플 소환사 더미 데이터"
            embed.set_footer(text=f"시뮬레이션 · {source_text} · 실제 전적/MMR/음성 채널에는 반영되지 않습니다.")
        if game_state.get("third_place_enabled"):
            embed.add_field(
                name="순위 결정",
                value="결승으로 1/2등, 3/4위전으로 3등까지 확정합니다.",
                inline=False,
            )
        return embed
    
    def build_league_series_match_detail_embed(guild, gid, match, matches, teams_by_no, game_state=None):
        team_nos = get_series_match_team_nos(match, matches)
        if len(team_nos) != 2:
            return None
        left_team = teams_by_no.get(int(team_nos[0]))
        right_team = teams_by_no.get(int(team_nos[1]))
        if not left_team or not right_team:
            return None
    
        left_total = int(left_team.get("total", left_team.get("display_total", 0)) or 0)
        right_total = int(right_team.get("total", right_team.get("display_total", 0)) or 0)
        gap = left_total - right_total
        if gap == 0:
            gap_text = "전력차 **0** · 균형"
        else:
            favored_no = left_team["team_no"] if gap > 0 else right_team["team_no"]
            gap_text = f"전력차 **{abs(gap)}** · {favored_no}팀 우세"
    
        round_name = match.get("round_name", "")
        round_label = f" [{round_name}]" if round_name else ""
        series_name = get_series_mode_name(game_state or {})
        embed = discord.Embed(
            title=f"⚔️ {series_name}{round_label} 매치 {match.get('match_no')}",
            description=(
                f"🔵 **{format_league_team_name(left_team)}** `{left_total}` vs `{right_total}` "
                f"**{format_league_team_name(right_team)}** 🔴\n{gap_text}"
            ),
            color=0x3498db,
        )
        embed.add_field(
            name=f"BLUE · {format_league_team_name(left_team)}",
            value=format_league_series_role_lines(guild, gid, left_team),
            inline=False,
        )
        embed.add_field(
            name=f"RED · {format_league_team_name(right_team)}",
            value=format_league_series_role_lines(guild, gid, right_team),
            inline=False,
        )
        return embed
    
    def get_league_series_initial_bye_team_nos(game_state):
        matches = game_state.get("matches", {}) or {}
        first_round = min((int(match.get("round_index", 0) or 0) for match in matches.values()), default=0)
        playable_team_nos = set()
        later_direct_team_nos = set()
        for match in matches.values():
            round_index = int(match.get("round_index", 0) or 0)
            direct_team_nos = {int(slot["team_no"]) for slot in match.get("slots", []) if slot.get("team_no")}
            if round_index == first_round:
                playable_team_nos.update(direct_team_nos)
            elif direct_team_nos:
                later_direct_team_nos.update(direct_team_nos)
        return sorted(later_direct_team_nos - playable_team_nos)
    
    async def send_league_series_start_messages(interaction, gid, game_state, *, title_suffix="대진표", cut_names=None, simulation=False):
        send_output = send_league_sim_output if simulation else send_league_output
        embed = build_league_series_embed(interaction.guild, gid, game_state, title_suffix=title_suffix)
        team_count = int(game_state.get("team_count", 0) or 0)
        gap_limit_used = game_state.get("team_gap_limit_used")
        if gap_limit_used and gap_limit_used > get_league_team_gap_hard_limit(team_count):
            embed.description = f"{embed.description}\n팀 총점 격차 기준을 **{gap_limit_used}점**까지 완화해 구성했습니다."
        if cut_names:
            embed.add_field(
                name="컷 처리",
                value=f"마지막 신청자 {len(cut_names)}명 제외: " + ", ".join(cut_names[:10]),
                inline=False,
            )
        await send_output(interaction, gid, embed=embed, allowed_mentions=discord.AllowedMentions.none())
    
        teams_by_no = {int(team.get("team_no")): team for team in game_state.get("teams", [])}
        matches = game_state.get("matches", {}) or {}
        for match_id in game_state.get("match_order", []):
            match = matches.get(str(match_id), {})
            if not is_series_match_playable(match, matches):
                continue
            detail_embed = build_league_series_match_detail_embed(interaction.guild, gid, match, matches, teams_by_no, game_state)
            if detail_embed:
                await send_output(
                    interaction,
                    gid,
                    embed=detail_embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                    notify=False,
                )
    
        for team_no in get_league_series_initial_bye_team_nos(game_state):
            team = teams_by_no.get(int(team_no))
            if not team:
                continue
            bye_embed = discord.Embed(
                title="💤 부전승",
                description=f"**{format_league_team_name(team)}**은 예비 라운드를 건너뛰고 다음 라운드에 진출합니다.",
                color=0x95a5a6,
            )
            bye_embed.add_field(
                name=f"{format_league_team_name(team)} · 총점 {team.get('total', 0)}",
                value=format_league_series_role_lines(interaction.guild, gid, team),
                inline=False,
            )
            await send_output(
                interaction,
                gid,
                embed=bye_embed,
                allowed_mentions=discord.AllowedMentions.none(),
                notify=False,
            )
    
    async def league_series_lineup(interaction: discord.Interaction, third_place: bool = False):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "league"):
            return await interaction.response.send_message(get_disabled_feature_message("league"), ephemeral=True)
    
        active_state = bot.active_games.get(gid, {}).get(LEAGUE_SERIES_QUEUE_KEY)
        if active_state and not active_state.get("finalized"):
            embed = build_league_series_embed(
                interaction.guild,
                gid,
                active_state,
                title_suffix="진행 중 대진표",
            )
            return await interaction.response.send_message(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
    
        q = ensure_guild_queues(gid).get(LEAGUE_SERIES_QUEUE_KEY, [])
        usable_count = min(len(q), LEAGUE_SERIES_MAX_PLAYER_COUNT)
        usable_count -= usable_count % len(ROLES)
        team_count = usable_count // len(ROLES)
        cut_count = len(q) - usable_count
        if team_count < LEAGUE_SERIES_MIN_TEAM_COUNT:
            return await interaction.response.send_message(
                f"❌ {LEAGUE_SERIES_MODE_NAME} 팀구성 실패: 최소 15명(3팀)이 필요합니다. 현재 {len(q)}명",
                ephemeral=True,
            )
    
        operation_key = bot.begin_admin_operation(gid, "league_series_lineup")
        if not operation_key:
            return await reject_duplicate_admin_operation(interaction, "협곡 리그전 팀구성")
    
        try:
            await interaction.response.defer()
            selected_q = q[:usable_count]
            teams, error = build_league_teams(
                gid,
                selected_q,
                team_count=team_count,
                mode_name=LEAGUE_SERIES_MODE_NAME,
                team_gap_soft_limit=LEAGUE_SERIES_TEAM_GAP_SOFT_LIMIT,
                lane_gap_soft_limit=LEAGUE_SERIES_LANE_GAP_HEAVY_LIMIT,
                lane_gap_heavy_limit=LEAGUE_SERIES_LANE_GAP_HEAVY_LIMIT,
            )
            if error:
                return await interaction.followup.send(error)
    
            bracket = build_league_series_bracket(team_count, third_place=third_place)
            third_place_enabled = any(match.get("placement") == "third_place" for match in bracket["matches"].values())
            round_no = get_next_league_series_round(gid)
            bot.active_games.setdefault(gid, {})[LEAGUE_SERIES_QUEUE_KEY] = initialize_active_game_state(gid, LEAGUE_SERIES_QUEUE_KEY, {
                "mode": LEAGUE_SERIES_MODE_KEY,
                "round_no": round_no,
                "queue_snapshot": list(selected_q),
                "team_count": team_count,
                "third_place_enabled": third_place_enabled,
                "teams": [
                    {
                        "name": team["name"],
                        "team_no": team["team_no"],
                        "total": team.get("display_total", team["total"]),
                        "weighted_total": team["total"],
                        "players": team["player_ids"],
                        "roles": {role: team["players"][role]["uid"] for role in ROLES},
                        "player_names": {team["players"][role]["uid"]: team["players"][role]["name"] for role in ROLES},
                        "player_scores": {team["players"][role]["uid"]: team["players"][role]["score"] for role in ROLES},
                    }
                    for team in teams
                ],
                "matches": bracket["matches"],
                "match_order": bracket["match_order"],
                "finalized": False,
                "team_gap_limit_used": teams[0].get("_team_gap_limit_used"),
            })
            _persist_active_game(gid, bot.active_games[gid][LEAGUE_SERIES_QUEUE_KEY])
            ensure_guild_queues(gid)[LEAGUE_SERIES_QUEUE_KEY] = []
            bot.save_lucid_data(gid)
    
            cut_names = []
            if cut_count > 0:
                for data in q[usable_count:]:
                    user, *_ = normalize_queue_entry(data)
                    cut_names.append(user.display_name)
            await send_league_series_start_messages(
                interaction,
                gid,
                bot.active_games[gid][LEAGUE_SERIES_QUEUE_KEY],
                cut_names=cut_names,
            )
    
            await create_and_move_team_voice_channels(
                interaction.guild,
                [
                    (
                        f"🏆 {LEAGUE_SERIES_MODE_NAME} {team['team_no']}팀",
                        [team["players"][role]["user"] for role in ROLES],
                    )
                    for team in teams
                ],
                move_members=False,
                game_state=bot.active_games[gid][LEAGUE_SERIES_QUEUE_KEY],
            )
        finally:
            bot.finish_admin_operation(operation_key)
    
    async def aram_league_series_lineup(interaction: discord.Interaction, third_place: bool = False):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "aram"):
            return await interaction.response.send_message(get_disabled_feature_message("aram"), ephemeral=True)
    
        active_state = bot.active_games.get(gid, {}).get(ARAM_LEAGUE_QUEUE_KEY)
        if active_state and not active_state.get("finalized"):
            embed = build_league_series_embed(interaction.guild, gid, active_state, title_suffix="진행 중 대진표")
            return await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    
        q = ensure_guild_queues(gid).get(ARAM_LEAGUE_QUEUE_KEY, [])
        usable_count = min(len(q), ARAM_LEAGUE_MAX_PLAYER_COUNT)
        usable_count -= usable_count % 5
        team_count = usable_count // 5
        cut_count = len(q) - usable_count
        if team_count < ARAM_LEAGUE_MIN_TEAM_COUNT:
            return await interaction.response.send_message(
                f"❌ {ARAM_LEAGUE_MODE_NAME} 팀구성 실패: 최소 15명(3팀)이 필요합니다. 현재 {len(q)}명",
                ephemeral=True,
            )
    
        operation_key = bot.begin_admin_operation(gid, "aram_league_series_lineup")
        if not operation_key:
            return await reject_duplicate_admin_operation(interaction, f"{ARAM_LEAGUE_MODE_NAME} 팀구성")
    
        try:
            await interaction.response.defer()
            selected_q = q[:usable_count]
            teams, error = build_aram_league_teams(gid, selected_q, team_count)
            if error:
                return await interaction.followup.send(error)
    
            bracket = build_league_series_bracket(team_count, third_place=third_place)
            third_place_enabled = any(match.get("placement") == "third_place" for match in bracket["matches"].values())
            round_no = get_next_aram_league_round(gid)
            stored_teams = []
            for team in teams:
                stored_teams.append({
                    "name": team["name"],
                    "team_no": team["team_no"],
                    "total": team["total"],
                    "weighted_total": team["total"],
                    "players": list(team["player_ids"]),
                    "roles": {},
                    "player_names": dict(team["player_names"]),
                    "player_scores": dict(team["player_scores"]),
                })
            bot.active_games.setdefault(gid, {})[ARAM_LEAGUE_QUEUE_KEY] = initialize_active_game_state(gid, ARAM_LEAGUE_QUEUE_KEY, {
                "mode": ARAM_LEAGUE_MODE_KEY,
                "queue_key": ARAM_LEAGUE_QUEUE_KEY,
                "round_no": round_no,
                "queue_snapshot": list(selected_q),
                "team_count": team_count,
                "third_place_enabled": third_place_enabled,
                "teams": stored_teams,
                "matches": bracket["matches"],
                "match_order": bracket["match_order"],
                "finalized": False,
            })
            _persist_active_game(gid, bot.active_games[gid][ARAM_LEAGUE_QUEUE_KEY])
            ensure_guild_queues(gid)[ARAM_LEAGUE_QUEUE_KEY] = []
            bot.save_lucid_data(gid)
    
            cut_names = []
            if cut_count > 0:
                for data in q[usable_count:]:
                    user, *_ = normalize_queue_entry(data)
                    cut_names.append(user.display_name)
            await send_league_series_start_messages(
                interaction, gid, bot.active_games[gid][ARAM_LEAGUE_QUEUE_KEY], cut_names=cut_names
            )
    
            user_by_id = {}
            for data in selected_q:
                user, *_ = normalize_queue_entry(data)
                user_by_id[str(user.id)] = user
            await create_and_move_team_voice_channels(
                interaction.guild,
                [
                    (f"❄️ {ARAM_LEAGUE_MODE_NAME} {team['team_no']}팀", [user_by_id[uid] for uid in team["player_ids"] if uid in user_by_id])
                    for team in teams
                ],
                move_members=False,
                game_state=bot.active_games[gid][ARAM_LEAGUE_QUEUE_KEY],
            )
        finally:
            bot.finish_admin_operation(operation_key)
    
    def build_dummy_league_series_queue(team_count=LEAGUE_SERIES_MAX_TEAM_COUNT):
        sim_gid = f"league-series-sim-{random.randint(100000, 999999)}"
        bot.user_data.setdefault(sim_gid, {})
        q = []
        uid_base = random.randint(3000000, 9000000)
        for idx in range(int(team_count) * len(ROLES)):
            uid = str(uid_base + idx)
            name = f"리그전소환사{idx + 1:02}"
            mmr = {}
            plays = {}
            primary_role = ROLES[idx % len(ROLES)]
            for role in ROLES:
                base = random.randint(900, 2600)
                mmr[role] = base + (80 if role == primary_role else 0)
                plays[role] = 5 if role == primary_role else 1
            bot.user_data[sim_gid][uid] = ensure_user_format({
                "lol_name": name,
                "mmr": mmr,
                "plays": plays,
            })
            q.append((LeagueSimulationUser(uid, name), time.time(), primary_role, None, None))
        return sim_gid, q
    
    def build_league_series_sim_candidates_from_user_data(gid):
        candidates = []
        guild_data = bot.user_data.get(gid, {}) or {}
        for uid, raw_info in guild_data.items():
            if str(uid).startswith("_") or not isinstance(raw_info, dict):
                continue
            if is_simulation_user_record(uid, raw_info):
                continue
            user_info = ensure_user_format(raw_info)
            placed_roles = [
                role for role in ROLES
                if user_info.get("mmr", {}).get(role, 0) > 0
                and user_info.get("plays", {}).get(role, 0) > 0
            ]
            if placed_roles:
                name = user_info.get("lol_name") or f"유저 {uid}"
                candidates.append((str(uid), name, placed_roles))
        return candidates
    
    async def league_series_lineup_simulation(interaction: discord.Interaction, team_count=None, third_place: bool = False):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        active_state = bot.active_games.get(gid, {}).get(LEAGUE_SERIES_SIM_QUEUE_KEY)
        if active_state and not active_state.get("finalized"):
            return await interaction.response.send_message(
                f"⚠️ 이미 진행 중인 {LEAGUE_SERIES_SIM_LABEL} 세션이 있습니다. 결승까지 완료한 뒤 다시 생성해주세요.",
                ephemeral=True,
            )
    
        if team_count is None:
            guild_data = bot.user_data.setdefault(gid, {})
            choices = list(range(LEAGUE_SERIES_MIN_TEAM_COUNT, LEAGUE_SERIES_MAX_TEAM_COUNT + 1))
            last_team_count = guild_data.get(LEAGUE_SERIES_SIM_LAST_TEAM_COUNT_KEY)
            if len(choices) > 1 and last_team_count in choices:
                choices.remove(last_team_count)
            team_count = random.choice(choices)
            guild_data[LEAGUE_SERIES_SIM_LAST_TEAM_COUNT_KEY] = team_count
        team_count = max(LEAGUE_SERIES_MIN_TEAM_COUNT, min(LEAGUE_SERIES_MAX_TEAM_COUNT, int(team_count)))
        await interaction.response.defer()
        required_count = int(team_count) * len(ROLES)
        candidates = build_league_series_sim_candidates_from_user_data(gid)
        sim_gid = None
        q = None
        teams = None
        error = None
        used_dummy = False
        try:
            if len(candidates) >= required_count:
                for _ in range(200):
                    sample_try = random.sample(candidates, required_count)
                    source_q = [
                        (LeagueSimulationUser(uid, name), time.time(), None, None, None, roles)
                        for uid, name, roles in sample_try
                    ]
                    teams, error = build_league_teams(
                        gid,
                        source_q,
                        team_count=team_count,
                        mode_name=LEAGUE_SERIES_MODE_NAME,
                        team_gap_soft_limit=LEAGUE_SERIES_TEAM_GAP_SOFT_LIMIT,
                        lane_gap_soft_limit=LEAGUE_SERIES_LANE_GAP_HEAVY_LIMIT,
                        lane_gap_heavy_limit=LEAGUE_SERIES_LANE_GAP_HEAVY_LIMIT,
                    )
                    if teams:
                        q = source_q
                        break
    
            if not teams:
                sim_gid, q = build_dummy_league_series_queue(team_count)
                used_dummy = True
                teams, error = build_league_teams(
                    sim_gid,
                    q,
                    team_count=team_count,
                    mode_name=LEAGUE_SERIES_MODE_NAME,
                    team_gap_soft_limit=LEAGUE_SERIES_TEAM_GAP_SOFT_LIMIT,
                    lane_gap_soft_limit=LEAGUE_SERIES_LANE_GAP_HEAVY_LIMIT,
                    lane_gap_heavy_limit=LEAGUE_SERIES_LANE_GAP_HEAVY_LIMIT,
                )
            if error:
                return await interaction.followup.send(error, ephemeral=True)
            bracket = build_league_series_bracket(team_count, third_place=third_place)
            third_place_enabled = any(match.get("placement") == "third_place" for match in bracket["matches"].values())
            game_state = {
                "mode": LEAGUE_SERIES_MODE_KEY,
                "simulation": True,
                "round_no": get_next_league_series_round(gid),
                "team_count": team_count,
                "third_place_enabled": third_place_enabled,
                "teams": [
                    {
                        "name": f"{LEAGUE_SERIES_MODE_NAME} {team['team_no']}팀",
                        "team_no": team["team_no"],
                        "total": team.get("display_total", team["total"]),
                        "weighted_total": team["total"],
                        "players": team["player_ids"],
                        "roles": {role: team["players"][role]["uid"] for role in ROLES},
                        "player_names": {team["players"][role]["uid"]: team["players"][role]["name"] for role in ROLES},
                        "player_scores": {team["players"][role]["uid"]: team["players"][role]["score"] for role in ROLES},
                    }
                    for team in teams
                ],
                "matches": bracket["matches"],
                "match_order": bracket["match_order"],
                "finalized": False,
                "team_gap_limit_used": teams[0].get("_team_gap_limit_used"),
                "sim_used_dummy": used_dummy,
            }
            bot.active_games.setdefault(gid, {})[LEAGUE_SERIES_SIM_QUEUE_KEY] = initialize_active_game_state(
                gid,
                LEAGUE_SERIES_SIM_QUEUE_KEY,
                game_state,
            )
            await send_league_series_start_messages(
                interaction,
                gid,
                game_state,
                title_suffix="시뮬레이션 대진표",
                simulation=True,
            )
        finally:
            if sim_gid:
                bot.user_data.pop(sim_gid, None)
    
    @app_commands.describe(시뮬레이션="실제 대기열 대신 협곡 리그전 시뮬레이션 세션을 생성합니다.")
    async def league_lineup(interaction: discord.Interaction, 시뮬레이션: bool = False):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "league"):
            return await interaction.response.send_message(get_disabled_feature_message("league"), ephemeral=True)
        if 시뮬레이션:
            return await league_lineup_simulation(interaction, create_session=True, include_queue_progress=False)
        active_state = bot.active_games.get(gid, {}).get(LEAGUE_QUEUE_KEY)
        if active_state and not active_state.get("finalized"):
            return await interaction.response.send_message(
                f"⚠️ 이미 진행 중인 {LEAGUE_MODE_NAME}이 있습니다. 현재 대진이 끝난 뒤 다시 팀구성을 진행해주세요.",
                ephemeral=True
            )
        operation_key = bot.begin_admin_operation(gid, "league_lineup")
        if not operation_key:
            return await reject_duplicate_admin_operation(interaction, "토너먼트팀구성")
    
        try:
            q = ensure_guild_queues(gid).get(LEAGUE_QUEUE_KEY, [])
            if len(q) < LEAGUE_PLAYER_COUNT:
                return await interaction.response.send_message(
                    f"❌ {LEAGUE_MODE_NAME} 대기 인원이 부족합니다. 현재 ({len(q)}/{LEAGUE_PLAYER_COUNT})명",
                    ephemeral=True
                )
    
            await interaction.response.defer()
            teams, error = build_league_teams(gid, q)
            if error:
                return await interaction.followup.send(error)
    
            totals = [team["total"] for team in teams]
            gap_limit_used = teams[0].get("_team_gap_limit_used")
            gap_limit_text = (
                f"\n팀 총점 격차 기준을 **{gap_limit_used}점**까지 완화해 구성했습니다."
                if gap_limit_used and gap_limit_used > get_league_team_gap_hard_limit(LEAGUE_TEAM_COUNT)
                else ""
            )
            league_matchups = build_league_matchups(teams)
            teams_by_no = {team["team_no"]: team for team in teams}
            stored_teams = [
                {
                    "name": team["name"],
                    "team_no": team["team_no"],
                    "total": team.get("display_total", team["total"]),
                    "weighted_total": team["total"],
                    "players": team["player_ids"],
                    "roles": {role: team["players"][role]["uid"] for role in ROLES},
                    "player_names": {team["players"][role]["uid"]: team["players"][role]["name"] for role in ROLES},
                    "player_scores": {team["players"][role]["uid"]: team["players"][role]["score"] for role in ROLES},
                }
                for team in teams
            ]
            stored_teams_by_no = {team["team_no"]: team for team in stored_teams}
    
            embed = discord.Embed(
                title=f"🏆 {LEAGUE_MODE_NAME} {get_next_league_round(gid)}회차 팀 구성 및 대진표",
                description=(
                    f"20명을 **5명씩 4팀**으로 배정했습니다.\n"
                    f"팀 평균 총점 **{round(sum(totals) / len(totals))}** · 최대 격차 **{max(totals) - min(totals)}**"
                    f"{gap_limit_text}\n```text\n{build_league_4team_bracket_diagram(league_matchups)}\n```"
                ),
                color=0x9b59b6
            )
            def build_league_team_lines(team):
                lines = []
                for role in ROLES:
                    player = team["players"][role]
                    tier_name = get_tier_name(player["score"])
                    lines.append(f"{format_match_role_score(role, player['score'], interaction.guild, gid)} {player['user'].mention}")
                return "\n".join(lines)
    
            def build_league_matchup_lines(left_team, right_team):
                lines = []
                left_no = left_team["team_no"]
                right_no = right_team["team_no"]
                for role in ROLES:
                    left_score = left_team["players"][role]["score"]
                    right_score = right_team["players"][role]["score"]
                    gap = left_score - right_score
                    if abs(gap) <= 10:
                        gap_text = "⚪ 거의 동률"
                    elif gap > 0:
                        gap_text = f"🟣 {left_no}팀 +{gap}"
                    else:
                        gap_text = f"🟠 {right_no}팀 +{abs(gap)}"
                    lines.append(f"**[{role}]** {gap_text}")
                return "\n".join(lines)
    
            def build_league_average_line(left_team, right_team):
                left_total = left_team.get("display_total", left_team["total"])
                right_total = right_team.get("display_total", right_team["total"])
                left_avg = round(left_total / len(ROLES))
                right_avg = round(right_total / len(ROLES))
                avg_gap = left_avg - right_avg
                if avg_gap == 0:
                    gap_text = "⚪ 팀 평균 동률"
                elif avg_gap > 0:
                    gap_text = f"🟣 {left_team['team_no']}팀 +{avg_gap}"
                else:
                    gap_text = f"🟠 {right_team['team_no']}팀 +{abs(avg_gap)}"
                return f"{left_team['team_no']}팀 `{left_avg}점` vs {right_team['team_no']}팀 `{right_avg}점`\n{gap_text}"
    
            def build_league_power_gap_line(blue_team, red_team):
                blue_total = blue_team.get("display_total", blue_team["total"])
                red_total = red_team.get("display_total", red_team["total"])
                gap = blue_total - red_total
                if gap == 0:
                    return "전력차 **0** · 균형"
                favored_no = blue_team["team_no"] if gap > 0 else red_team["team_no"]
                return f"전력차 **{abs(gap)}** · {favored_no}팀 우세"
    
            def build_league_match_field_value(blue_team, red_team):
                blue_total = blue_team.get("display_total", blue_team["total"])
                red_total = red_team.get("display_total", red_team["total"])
                return (
                    f"🔵 **{blue_team['team_no']}팀** `{blue_total}`  vs  `{red_total}` **{red_team['team_no']}팀** 🔴\n"
                    f"{build_league_power_gap_line(blue_team, red_team)}\n\n"
                    f"**BLUE {blue_team['team_no']}팀**\n"
                    f"{build_league_team_lines(blue_team)}\n\n"
                    f"**RED {red_team['team_no']}팀**\n"
                    f"{build_league_team_lines(red_team)}"
                )
    
            def build_league_role_assignment_embed():
                role_lines = []
                for role in ROLES:
                    players = [
                        team["players"][role]["user"].mention
                        for team in teams
                    ]
                    role_lines.append(f"{get_role_display_marker(role, interaction.guild)} : {', '.join(players)}")
    
                reveal_embed = discord.Embed(
                    title=f"🏆 {LEAGUE_MODE_NAME} {get_next_league_round(gid)}회차 라인 배정 결과",
                    description="\n".join(role_lines),
                    color=0x9b59b6
                )
                reveal_embed.set_footer(text="잠시 후 팀 추첨이 시작됩니다.")
                return reveal_embed
    
            def build_league_reveal_embed(revealed_slots=None, phase_text=f"{LEAGUE_MODE_NAME} 팀 추첨 시작"):
                revealed_slots = revealed_slots or set()
                reveal_embed = discord.Embed(
                    title=f"🎲 {phase_text}",
                    description="라인별로 1팀부터 4팀까지 순서대로 공개됩니다.",
                    color=0x9b59b6
                )
                for team in teams:
                    lines = []
                    for role in ROLES:
                        key = (team["team_no"], role)
                        if key in revealed_slots:
                            player = team["players"][role]
                            lines.append(f"{format_match_role_score(role, player['score'], interaction.guild, gid)} {player['user'].mention}")
                        else:
                            lines.append(f"{get_role_display_marker(role, interaction.guild)} ???")
                    reveal_embed.add_field(
                        name=f"{LEAGUE_MODE_NAME} {team['team_no']}팀",
                        value="\n".join(lines),
                        inline=False
                    )
                revealed_count = len(revealed_slots)
                reveal_embed.set_footer(text=f"공개 진행도 {revealed_count}/{LEAGUE_PLAYER_COUNT}")
                return reveal_embed
    
            async def send_or_edit_league_reveal(final_embed):
                output_channel = await get_league_output_channel(interaction.guild, gid)
                target_channel = output_channel if output_channel and output_channel.id != interaction.channel_id else None
    
                reveal_message = None
                first_embed = build_league_role_assignment_embed()
                if target_channel:
                    await target_channel.send(embed=first_embed)
                    await asyncio.sleep(15)
                    reveal_message = await target_channel.send(embed=build_league_reveal_embed())
                    await interaction.followup.send(f"✅ {LEAGUE_MODE_NAME} 팀 추첨을 {target_channel.mention} 채널에서 진행합니다.", ephemeral=True)
                else:
                    await interaction.followup.send(embed=first_embed)
                    await asyncio.sleep(15)
                    reveal_message = await interaction.followup.send(embed=build_league_reveal_embed(), wait=True)
    
                revealed_slots = set()
                await asyncio.sleep(2)
    
                for role in ROLES:
                    for team in teams:
                        revealed_slots.add((team["team_no"], role))
                        player = team["players"][role]
                        phase_text = f"{LEAGUE_MODE_NAME} 팀 추첨 중 · {team['team_no']}팀 {role} 공개"
                        await reveal_message.edit(embed=build_league_reveal_embed(revealed_slots, phase_text))
                        await asyncio.sleep(2)
    
                await reveal_message.edit(embed=final_embed)
                for detail_embed in match_detail_embeds:
                    if target_channel:
                        await target_channel.send(
                            embed=detail_embed,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    else:
                        await interaction.followup.send(
                            embed=detail_embed,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
    
            embed.add_field(
                name="🏁 협곡 리그전 [결승] 매치 3 · 아직 대진 미정",
                value=(
                    "매치 1 승리팀 vs 매치 2 승리팀\n"
                    f"`/승리 {LEAGUE_MODE_NAME} 1 [승리팀번호]`, `/승리 {LEAGUE_MODE_NAME} 2 [승리팀번호]` 입력 후 결승 대진이 표시됩니다."
                ),
                inline=False
            )
            match_detail_embeds = [
                build_league_match_detail_embed(
                    interaction.guild,
                    gid,
                    idx,
                    stored_teams_by_no[matchup[0]],
                    stored_teams_by_no[matchup[1]],
                    footer_text="실제 협곡 리그전 대기열 참가자 기준입니다.",
                )
                for idx, matchup in enumerate(league_matchups, 1)
            ]
    
            bot.active_games.setdefault(gid, {})[LEAGUE_QUEUE_KEY] = initialize_active_game_state(gid, LEAGUE_QUEUE_KEY, {
                "mode": LEAGUE_MODE_KEY,
                "round_no": get_next_league_round(gid),
                "queue_snapshot": list(q[:LEAGUE_PLAYER_COUNT]),
                "teams": stored_teams,
                "matches": {
                    "1": {"team_nos": league_matchups[0], "winner": None},
                    "2": {"team_nos": league_matchups[1], "winner": None},
                    "3": {"team_nos": [], "winner": None},
                },
                "finalized": False,
            })
            _persist_active_game(gid, bot.active_games[gid][LEAGUE_QUEUE_KEY])
            ensure_guild_queues(gid)[LEAGUE_QUEUE_KEY] = []
            bot.save_lucid_data(gid)
    
            await create_and_move_team_voice_channels(
                interaction.guild,
                [
                    (
                        f"🏆 {LEAGUE_MODE_NAME} {team['team_no']}팀",
                        [team["players"][role]["user"] for role in ROLES],
                    )
                    for team in teams
                ],
                move_members=False,
                game_state=bot.active_games[gid][LEAGUE_QUEUE_KEY],
            )
            await send_or_edit_league_reveal(embed)
        finally:
            bot.finish_admin_operation(operation_key)
    
    @bot.tree.command(name="협곡리그전팀구성", description="[내전 관리자] 협곡 리그전 15~40명을 3~8팀으로 구성하고 대진표를 생성합니다.")
    @app_commands.describe(시뮬레이션="실제 대기열 대신 협곡 리그전 시뮬레이션 세션을 생성합니다.")
    async def tournament_lineup(interaction: discord.Interaction, 시뮬레이션: bool = False):
        if 시뮬레이션:
            return await league_series_lineup_simulation(interaction)
        return await league_series_lineup(interaction)
    
    async def league_lineup_simulation(
        interaction: discord.Interaction,
        *,
        queue_only: bool = False,
        include_queue_progress: bool = True,
        create_session: bool = False,
        prepare_queue: bool = False,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        if create_session:
            gid = str(interaction.guild_id)
            active_state = bot.active_games.get(gid, {}).get(LEAGUE_SIM_QUEUE_KEY)
            if active_state and not active_state.get("finalized"):
                return await interaction.response.send_message(
                    f"⚠️ 이미 진행 중인 {LEAGUE_SIM_LABEL} 세션이 있습니다. 결승까지 완료한 뒤 다시 생성해주세요.",
                    ephemeral=True
                )
            include_queue_progress = False
    
        gid = str(interaction.guild_id)
        guild_data = bot.user_data.setdefault(gid, {})
        sim_pool_key = "_league_sim_queue_pool"
        sim_pool_used_dummy_key = "_league_sim_queue_used_dummy"
    
        def serialize_sim_queue(q, data_gid, dummy):
            serialized = []
            source_data = bot.user_data.get(data_gid, {})
            for data in q[:LEAGUE_PLAYER_COUNT]:
                user, _, _, _, _ = normalize_queue_entry(data)
                uid = str(user.id)
                roles = data[5] if len(data) > 5 and isinstance(data[5], list) else []
                raw_info = ensure_user_format(source_data.get(uid, {"lol_name": user.display_name}))
                serialized.append({
                    "uid": uid,
                    "name": raw_info.get("lol_name") or user.display_name,
                    "roles": [role for role in roles if role in ROLES],
                    "mmr": dict(raw_info.get("mmr", {})),
                    "plays": dict(raw_info.get("plays", {})),
                    "dummy": bool(dummy),
                })
            return serialized
    
        def restore_sim_queue(pool):
            q = []
            for item in pool[:LEAGUE_PLAYER_COUNT]:
                uid = str(item.get("uid"))
                name = str(item.get("name") or f"소환사 {len(q) + 1}")
                roles = [role for role in item.get("roles", []) if role in ROLES]
                if not uid or not roles:
                    continue
                if item.get("dummy"):
                    guild_data[uid] = ensure_user_format({
                        "lol_name": name,
                        "mmr": item.get("mmr", {}),
                        "plays": item.get("plays", {role: 1 for role in ROLES}),
                        "_simulation_dummy": True,
                    })
                q.append((LeagueSimulationUser(uid, name), time.time(), None, None, None, roles))
            return q if len(q) >= LEAGUE_PLAYER_COUNT else None
    
        if prepare_queue and queue_only:
            await interaction.response.defer()
            sim_gid, q = build_dummy_league_queue()
            try:
                guild_data[sim_pool_key] = serialize_sim_queue(q, sim_gid, True)
                guild_data[sim_pool_used_dummy_key] = True
                embed = (
                    build_league_sim_queue_progress_embed(q, sim_gid, interaction.guild, gid)
                    if include_queue_progress else
                    build_league_sim_lineup_embed(q, sim_gid, interaction.guild, gid)
                )
                return await interaction.followup.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none()
                )
            finally:
                bot.user_data.pop(sim_gid, None)
    
        candidates = []
        for uid, raw_info in guild_data.items():
            if str(uid).startswith("_") or not isinstance(raw_info, dict):
                continue
            if is_simulation_user_record(uid, raw_info):
                continue
            user_info = ensure_user_format(raw_info)
            placed_roles = [
                role for role in ROLES
                if user_info.get("mmr", {}).get(role, 0) > 0
                and user_info.get("plays", {}).get(role, 0) > 0
            ]
            if placed_roles:
                name = user_info.get("lol_name") or f"유저 {uid}"
                candidates.append((str(uid), name, placed_roles))
    
        await interaction.response.defer()
    
        teams = None
        error = None
        used_dummy = False
        source_q = None
        stored_pool = guild_data.get(sim_pool_key) if create_session else None
        if isinstance(stored_pool, list) and len(stored_pool) >= LEAGUE_PLAYER_COUNT:
            source_q = restore_sim_queue(stored_pool)
            if source_q:
                teams, error = build_league_teams(gid, source_q)
                used_dummy = bool(guild_data.get(sim_pool_used_dummy_key))
    
        if not teams and len(candidates) >= LEAGUE_PLAYER_COUNT:
            for _ in range(200):
                sample_try = random.sample(candidates, LEAGUE_PLAYER_COUNT)
                q = [
                    (LeagueSimulationUser(uid, name), time.time(), None, None, None, roles)
                    for uid, name, roles in sample_try
                ]
                teams, error = build_league_teams(gid, q)
                if teams:
                    source_q = q
                    break
    
        if not teams:
            sim_gid, q = build_dummy_league_queue()
            try:
                teams, error = build_league_teams(sim_gid, q)
                used_dummy = True
                source_q = q
                if prepare_queue:
                    guild_data[sim_pool_key] = serialize_sim_queue(q, sim_gid, True)
                    guild_data[sim_pool_used_dummy_key] = True
            finally:
                bot.user_data.pop(sim_gid, None)
            if not teams:
                return await interaction.followup.send(
                    f"⚠️ {LEAGUE_MODE_NAME} 샘플을 만드는 중 문제가 생겼습니다.\n`{str(error)[:900]}`\n필요하면 이 내용 그대로 `/봇제작자문의`로 보내주세요.",
                    ephemeral=True
                )
        elif prepare_queue and source_q:
            guild_data[sim_pool_key] = serialize_sim_queue(source_q, gid, used_dummy)
            guild_data[sim_pool_used_dummy_key] = used_dummy
    
        totals = [team.get("display_total", team["total"]) for team in teams]
        league_matchups = build_league_matchups(teams)
        teams_by_no = {team["team_no"]: team for team in teams}
        sim_round_no = get_next_league_round(gid)
        stored_teams = [
            {
                "name": f"{LEAGUE_MODE_NAME} {team['team_no']}팀",
                "team_no": team["team_no"],
                "total": team.get("display_total", team["total"]),
                "weighted_total": team["total"],
                "players": team["player_ids"],
                "roles": {role: team["players"][role]["uid"] for role in ROLES},
                "player_names": {team["players"][role]["uid"]: team["players"][role]["name"] for role in ROLES},
                "player_scores": {team["players"][role]["uid"]: team["players"][role]["score"] for role in ROLES},
            }
            for team in teams
        ]
        stored_teams_by_no = {team["team_no"]: team for team in stored_teams}
        match_detail_embeds = [
            build_league_match_detail_embed(
                interaction.guild,
                gid,
                idx,
                stored_teams_by_no[matchup[0]],
                stored_teams_by_no[matchup[1]],
                footer_text=(
                    "샘플 소환사 더미 데이터입니다. 실제 큐/전적/음성방에는 반영되지 않습니다."
                    if used_dummy else
                    "서버 실제 유저 랜덤 샘플입니다. 실제 큐/전적/음성방에는 반영되지 않습니다."
                ),
            )
            for idx, matchup in enumerate(league_matchups, 1)
        ]
    
        if create_session:
            bot.active_games.setdefault(gid, {})[LEAGUE_SIM_QUEUE_KEY] = initialize_active_game_state(gid, LEAGUE_SIM_QUEUE_KEY, {
                "mode": LEAGUE_MODE_KEY,
                "simulation": True,
                "round_no": sim_round_no,
                "teams": stored_teams,
                "matches": {
                    "1": {"team_nos": league_matchups[0], "winner": None},
                    "2": {"team_nos": league_matchups[1], "winner": None},
                    "3": {"team_nos": [], "winner": None},
                },
                "finalized": False,
                "team_gap_limit_used": teams[0].get("_team_gap_limit_used"),
            })
    
        def player_label(player):
            return f"`{discord.utils.escape_markdown(player['name'])}`"
    
        def build_team_lines(team):
            lines = []
            for role in ROLES:
                player = team["players"][role]
                tier_name = get_tier_name(player["score"])
                lines.append(f"{format_match_role_score(role, player['score'], interaction.guild, gid)} {player_label(player)}")
            return "\n".join(lines)
    
        def build_matchup_lines(left_team, right_team):
            lines = []
            left_no = left_team["team_no"]
            right_no = right_team["team_no"]
            for role in ROLES:
                left_score = left_team["players"][role]["score"]
                right_score = right_team["players"][role]["score"]
                gap = left_score - right_score
                if abs(gap) <= 10:
                    gap_text = "⚪ 거의 동률"
                elif gap > 0:
                    gap_text = f"🔵 {left_no}팀 +{gap}"
                else:
                    gap_text = f"🔴 {right_no}팀 +{abs(gap)}"
                lines.append(f"**[{role}]** {gap_text}")
            return "\n".join(lines)
    
        def build_average_line(left_team, right_team):
            left_total = left_team.get("display_total", left_team["total"])
            right_total = right_team.get("display_total", right_team["total"])
            left_avg = round(left_total / len(ROLES))
            right_avg = round(right_total / len(ROLES))
            avg_gap = left_avg - right_avg
            if avg_gap == 0:
                gap_text = "⚪ 팀 평균 동률"
            elif avg_gap > 0:
                gap_text = f"🔵 {left_team['team_no']}팀 +{avg_gap}"
            else:
                gap_text = f"🔴 {right_team['team_no']}팀 +{abs(avg_gap)}"
            return f"{left_team['team_no']}팀 `{left_avg}점` vs {right_team['team_no']}팀 `{right_avg}점`\n{gap_text}"
    
        def build_power_gap_line(blue_team, red_team):
            blue_total = blue_team.get("display_total", blue_team["total"])
            red_total = red_team.get("display_total", red_team["total"])
            gap = blue_total - red_total
            if gap == 0:
                return "전력차 **0** · 균형"
            favored_no = blue_team["team_no"] if gap > 0 else red_team["team_no"]
            return f"전력차 **{abs(gap)}** · {favored_no}팀 우세"
    
        def build_match_field_value(blue_team, red_team):
            blue_total = blue_team.get("display_total", blue_team["total"])
            red_total = red_team.get("display_total", red_team["total"])
            return (
                f"🔵 **{blue_team['team_no']}팀** `{blue_total}`  vs  `{red_total}` **{red_team['team_no']}팀** 🔴\n"
                f"{build_power_gap_line(blue_team, red_team)}\n\n"
                f"**BLUE {blue_team['team_no']}팀**\n"
                f"{build_team_lines(blue_team)}\n\n"
                f"**RED {red_team['team_no']}팀**\n"
                f"{build_team_lines(red_team)}"
            )
    
        def build_role_assignment_embed():
            role_lines = []
            for role in ROLES:
                players = [player_label(team["players"][role]) for team in teams]
                role_lines.append(f"{get_role_display_marker(role, interaction.guild)} : {', '.join(players)}")
            embed = discord.Embed(
                title=f"🧪 {LEAGUE_MODE_NAME} 시뮬레이션 · 라인 배정 결과",
                description="\n".join(role_lines),
                color=0x9b59b6
            )
            footer_text = (
                "소환사 1~20과 랜덤 점수(800~3200점)로 만든 샘플입니다. 실제 큐/전적/음성방에는 반영되지 않습니다."
                if used_dummy else
                "실제 배치 기록이 있는 라인만 기준으로 사용합니다. 실제 큐/전적/음성방에는 반영되지 않습니다."
            )
            embed.set_footer(text=footer_text)
            return embed
    
        def build_queue_progress_embed():
            ordered_players = []
            for team in teams:
                for role in ROLES:
                    player = team["players"][role]
                    ordered_players.append((player["name"], role, player["score"]))
            random.shuffle(ordered_players)
    
            lines = []
            for idx, (name, role, score) in enumerate(ordered_players, 1):
                filled = "■" * idx
                empty = "□" * (LEAGUE_PLAYER_COUNT - idx)
                lines.append(
                    f"`{idx:02}/{LEAGUE_PLAYER_COUNT}` {filled}{empty} "
                    f"{discord.utils.escape_markdown(name)} · {role} `{get_public_mmr_rank(score)}`"
                )
    
            embed = discord.Embed(
                title=f"🧪 {LEAGUE_MODE_NAME} 시뮬레이션 · 대기열 신청 흐름",
                description="\n".join(lines),
                color=0x9b59b6
            )
            embed.set_footer(text=f"시뮬레이션 20명 풀이 준비되었습니다. /내전진행 작업:팀구성 큐:{LEAGUE_SIM_LABEL} 입력 시 이 풀로 팀과 대진표를 생성합니다.")
            return embed
    
        if queue_only:
            return await send_league_sim_output(
                interaction,
                gid,
                embed=build_queue_progress_embed(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
    
        def build_reveal_embed(revealed_slots=None, phase_text=f"{LEAGUE_MODE_NAME} 팀 추첨 시작"):
            revealed_slots = revealed_slots or set()
            embed = discord.Embed(
                title=f"🎲 시뮬레이션 · {phase_text}",
                description="라인별로 1팀부터 4팀까지 순서대로 공개됩니다.",
                color=0x9b59b6
            )
            for team in teams:
                lines = []
                for role in ROLES:
                    key = (team["team_no"], role)
                    if key in revealed_slots:
                        player = team["players"][role]
                        lines.append(f"{format_match_role_score(role, player['score'], interaction.guild, gid)} {player_label(player)}")
                    else:
                        lines.append(f"{get_role_display_marker(role, interaction.guild)} ???")
                embed.add_field(name=f"{LEAGUE_MODE_NAME} {team['team_no']}팀", value="\n".join(lines), inline=False)
            embed.set_footer(text=f"공개 진행도 {len(revealed_slots)}/{LEAGUE_PLAYER_COUNT}")
            return embed
    
        def build_final_embed():
            gap_limit_used = teams[0].get("_team_gap_limit_used")
            gap_limit_text = (
                f"\n팀 총점 격차 기준을 **{gap_limit_used}점**까지 완화해 구성했습니다."
                if gap_limit_used and gap_limit_used > get_league_team_gap_hard_limit(LEAGUE_TEAM_COUNT)
                else ""
            )
            embed = discord.Embed(
                title=f"🧪 {LEAGUE_MODE_NAME} 시뮬레이션 · 최종 팀 구성 및 대진표",
                description=(
                    f"{'소환사 1~20 샘플' if used_dummy else '랜덤 20명'}으로 구성한 미리보기입니다.\n"
                    f"팀 평균 총점 **{round(sum(totals) / len(totals))}** · 최대 격차 **{max(totals) - min(totals)}**\n"
                    f"결승 대진은 매치 1과 매치 2 결과를 입력한 뒤 표시됩니다.{gap_limit_text}\n"
                    f"```text\n{build_league_4team_bracket_diagram(league_matchups)}\n```"
                ),
                color=0x9b59b6
            )
            embed.add_field(
                name="🏁 협곡 리그전 [결승] 매치 3 · 아직 대진 미정",
                value=(
                    "매치 1 승리팀 vs 매치 2 승리팀\n"
                    f"`/승리 {LEAGUE_SIM_LABEL} 1 [승리팀번호]`\n"
                    f"`/승리 {LEAGUE_SIM_LABEL} 2 [승리팀번호]`\n"
                    "두 결과가 모두 입력되면 결승 대진이 표시됩니다."
                ),
                inline=False
            )
            embed.add_field(
                name="🧾 결과 입력 흐름",
                value=(
                    f"`/내전진행 작업:팀구성 큐:{LEAGUE_SIM_LABEL}` 또는 `/협곡리그전팀구성 시뮬레이션:True` 로 시뮬레이션 세션을 시작한 뒤\n"
                    f"`/승리 {LEAGUE_SIM_LABEL} 1 [승리팀번호]` → 매치 1 결과 기록\n"
                    f"`/승리 {LEAGUE_SIM_LABEL} 2 [승리팀번호]` → 결승 대진 표시\n"
                    f"`/승리 {LEAGUE_SIM_LABEL} 3 [승리팀번호]` → 결승 결과 입력"
                ),
                inline=False
            )
            footer_text = (
                f"시뮬레이션 진행 세션이 생성되었습니다. /승리 대상:{LEAGUE_SIM_LABEL} 으로 결승까지 테스트할 수 있습니다."
                if create_session else
                f"미리보기 화면입니다. 결승까지 진행하려면 /내전진행 작업:팀구성 큐:{LEAGUE_SIM_LABEL} 또는 /협곡리그전팀구성 시뮬레이션:True 를 사용하세요."
            )
            embed.set_footer(text=footer_text)
            return embed
    
        if include_queue_progress:
            await send_league_sim_output(
                interaction,
                gid,
                embed=build_queue_progress_embed(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
    
        await send_league_sim_output(
            interaction,
            gid,
            embed=build_final_embed(),
            allowed_mentions=discord.AllowedMentions.none(),
            notify=False,
        )
        for detail_embed in match_detail_embeds:
            await send_league_sim_output(
                interaction,
                gid,
                embed=detail_embed,
                allowed_mentions=discord.AllowedMentions.none(),
                notify=False,
            )
        return
    
    async def internal_lineup(interaction: discord.Interaction, q_num: int):
        gid = str(interaction.guild_id)
        active_state = bot.active_games.get(gid, {}).get(q_num)
        if active_state:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            if active_state.get("mode") == EVENT_MODE_KEY:
                return await send_existing_arena_lineup(interaction, gid, q_num, active_state)
            if active_state.get("mode") == ARAM_MODE_KEY:
                return await send_existing_aram_lineup(interaction, gid, q_num, active_state)
            return await send_existing_classic_lineup(interaction, gid, q_num, active_state)
    
        process_key = (gid, q_num)
        if process_key in bot.processing_lineups:
            msg = f"⏳ {get_queue_label(q_num)} 라인업이 이미 계산 중입니다. 잠시만 기다려주세요."
            if interaction.response.is_done():
                return await interaction.followup.send(msg, ephemeral=True)
            return await interaction.response.send_message(msg, ephemeral=True)
    
        bot.processing_lineups.add(process_key)
        try:
            return await _internal_lineup_core(interaction, q_num)
        finally:
            bot.processing_lineups.discard(process_key)
    
    async def _internal_lineup_core(interaction: discord.Interaction, q_num: int):
        """
        10인 구성 완료 시 호출되는 시스템 코어 매칭 엔진 파이프라인.
        - 규칙 1: 마스터 이상 양 팀 공평 분산 분배
        - 규칙 2: 승리 라인 비중 2:3 강제 유지 및 바텀 캐리 시 진영 편입
        - 규칙 3: 미지망 라인 배제 및 1지망 고정 유저 엄격 심사
        - 규칙 4: 올라운더 유저의 조커 프리패스 활용
        - 규칙 5: 1~4번 규칙을 충족하는 최적의 맞라인 티어 매칭 (밸런싱)
        """
        gid = str(interaction.guild_id)
        q = bot.queues.get(gid, {}).get(q_num, [])
    
        if q_num == ARENA_QUEUE_NUM:
            return await internal_arena_lineup(interaction, q_num)
    
        if q_num == ARAM_QUEUE_KEY:
            return await internal_aram_lineup(interaction, q_num)
        
        if len(q) < 10: 
            if not interaction.response.is_done(): 
                return await interaction.response.send_message(f"❌ 매칭 구성 실패: 인원 부족 ({len(q)}/10)")
            return await interaction.followup.send(f"❌ 매칭 구성 실패: 인원 부족 ({len(q)}/10)")
    
        if not interaction.response.is_done(): 
            await interaction.response.defer()
    
        # MMR 2.1: 실제 MMR은 그대로 두고, 티어/라인 + 큐 내 상대위치 + 큐 수준별 라인 영향력을
        # 순수 +/- 점수로 합산해 라인업용 effective MMR만 계산합니다.
        queue_display_scores = []
        for p_data in q:
            user, _, pref1, pref2, pref3 = normalize_queue_entry(p_data)
            raw_info = bot.user_data.get(gid, {}).get(str(user.id), {})
            user_info = ensure_user_format(raw_info)
            queue_display_scores.append(get_noban_queue_display_mmr(user_info, pref1, pref2, pref3) if q_num == NOBAN_QUEUE_NUM else get_queue_display_mmr(user_info, pref1, pref2, pref3))
        queue_avg_mmr = round(sum(queue_display_scores) / len(queue_display_scores)) if queue_display_scores else 0
    
        def calculate_eff_mmr(ud, role):
            if q_num == NOBAN_QUEUE_NUM:
                return get_noban_queue_score(ud, role)
            base_mmr = int(ud['mmr'].get(role, 0) or 0)
            if base_mmr <= 0:
                return 0
            return base_mmr + get_additive_role_adjustment(
                base_mmr, role, queue_avg_mmr=queue_avg_mmr, queue_scores=queue_display_scores,
                low_queue=(q_num == LOW_TIER_QUEUE_KEY),
            )
    
        cache_eff = {}
        cache_pref = {}
        cache_avg_mmr = {}
        cache_peak_mmr = {}
        cache_role_mmr = {}
        uid_to_pdata = {}
        uids = []
        user_prefs = {}
    
        for p_data in q:
            user, _, pref1, pref2, pref3 = normalize_queue_entry(p_data)
            uid_str = str(user.id)
            uids.append(uid_str)
            uid_to_pdata[uid_str] = p_data
            user_prefs[uid_str] = (pref1, pref2, pref3)
            
            raw_info = bot.user_data.get(gid, {}).get(uid_str, {})
            ud = ensure_user_format(raw_info)
            requested_roles = get_requested_roles(pref1, pref2, pref3)
            forced_low_tier = q_num == LOW_TIER_QUEUE_KEY and is_low_tier_force_entry(p_data)
            if q_num == NOBAN_QUEUE_NUM:
                playable_roles = set(get_noban_effective_roles(ud, pref1, pref2, pref3))
            else:
                playable_roles = set(get_low_tier_roles(ud)) if q_num == LOW_TIER_QUEUE_KEY and not forced_low_tier else {r for r, score in ud['mmr'].items() if score > 0}
            if not playable_roles:
                msg = (
                    f"⚠️ {user.display_name}님은 저티어 큐에 신청 가능한 라인이 없습니다. "
                    f"라인별 MMR {LOW_TIER_MMR_LIMIT}점 이하인 배치 완료 라인만 참가할 수 있습니다."
                    if q_num == LOW_TIER_QUEUE_KEY and not forced_low_tier
                    else f"⚠️ {user.display_name}님은 노밴 MMR 또는 신청 가능한 일반 라인 MMR이 필요합니다."
                    if q_num == NOBAN_QUEUE_NUM
                    else format_mmr_eval_required_message(requested_roles, user.display_name)
                )
                if not interaction.response.is_done():
                    return await interaction.response.send_message(msg)
                return await interaction.followup.send(msg)
            unrated_roles = [role for role in requested_roles if role not in playable_roles]
            if unrated_roles:
                msg = (
                    f"⚠️ {user.display_name}님은 저티어 큐에서 신청할 수 없는 라인을 선택했습니다: `{', '.join(unrated_roles)}`\n"
                    f"라인별 MMR {LOW_TIER_MMR_LIMIT}점 이하인 배치 완료 라인만 가능합니다."
                    if q_num == LOW_TIER_QUEUE_KEY and not forced_low_tier
                    else format_mmr_eval_required_message(unrated_roles, user.display_name)
                )
                if not interaction.response.is_done():
                    return await interaction.response.send_message(msg)
                return await interaction.followup.send(msg)
            
            cache_avg_mmr[uid_str] = get_noban_queue_display_mmr(ud, pref1, pref2, pref3) if q_num == NOBAN_QUEUE_NUM else get_avg_mmr(ud['mmr'])
            cache_peak_mmr[uid_str] = get_noban_queue_display_mmr(ud, pref1, pref2, pref3) if q_num == NOBAN_QUEUE_NUM else get_peak_mmr(ud['mmr'])
            cache_role_mmr[uid_str] = (
                {r: get_noban_queue_score(ud, r) for r in ROLES}
                if q_num == NOBAN_QUEUE_NUM else
                {r: int(ud['mmr'].get(r, 0) or 0) for r in ROLES}
            )
            cache_eff[uid_str] = {r: calculate_eff_mmr(ud, r) for r in ROLES}
            
            cache_pref[uid_str] = {}
            for r in ROLES:
                cache_pref[uid_str][r] = get_lineup_preference_score(
                    (pref1, pref2, pref3), r, playable_roles
                )

        shared_lineup = None
        shared_lineup_failed = False
        if q_num not in (NOBAN_QUEUE_NUM, LOW_TIER_QUEUE_KEY):
            try:
                shared_lineup = find_classic_lineup(
                    [
                        LineupPlayerInput(uid, tuple(user_prefs[uid]), dict(cache_role_mmr[uid]))
                        for uid in uids
                    ],
                    LineupConfig(
                        separation_pairs=tuple(get_team_separation_pairs(gid)),
                        early_server=is_early_match_history_server(gid),
                        permutation_limit=LINEUP_PERM_LIMIT,
                    ),
                    rng=random,
                    clock=time.monotonic,
                )
            except LineupNotFoundError:
                shared_lineup_failed = True
    
        eligible_role_counts = {role: 0 for role in ROLES}
        effectively_fixed_count = 0
        for uid in uids:
            eligible_roles = [role for role in ROLES if cache_pref[uid].get(role, 0) > 0]
            for role in eligible_roles:
                eligible_role_counts[role] += 1
            if len(eligible_roles) == 1:
                effectively_fixed_count += 1
    
        hard_queue = (
            effectively_fixed_count >= 3
            or any(count <= 2 for count in eligible_role_counts.values())
            or any(count >= 6 for count in eligible_role_counts.values())
        )
        permutation_limit = 120 if hard_queue else LINEUP_PERM_LIMIT
    
        # 📌 [지망 완벽 배제 엔진] 본인이 신청하지 않은 라인의 조합은 시뮬레이션 단계부터 완전 차단
        def get_valid_permutations(team_uids):
            valid_perms = []
            for p in itertools.permutations(team_uids, 5):
                valid = True
                for i, uid in enumerate(p):
                    role = ROLES[i]
                    prefs = user_prefs[uid]
                    # 올라운더 프리패스(조커) 처리
                    if not get_requested_roles(*prefs): 
                        if cache_pref[uid][role] > 0:
                            continue
                        valid = False
                        break
                    # 미신청 라인 배치 불가 검증 로직
                    if role not in prefs:
                        valid = False
                        break
                if valid:
                    valid_perms.append(p)
            valid_perms.sort(
                key=lambda perm: (
                    sum(cache_pref[uid][ROLES[i]] for i, uid in enumerate(perm)),
                    -sum(cache_eff[uid][ROLES[i]] for i, uid in enumerate(perm))
                ),
                reverse=True
            )
            return select_diverse_permutations(valid_perms, permutation_limit)
    
        best_fitness_strict = float('-inf')
        best_match_strict = None
    
        best_fitness_display_strict = float('-inf')
        best_match_display_strict = None
    
        best_fitness_fallback = float('-inf')
        best_match_fallback = None
    
        best_fitness_relaxed = float('-inf')
        best_match_relaxed = None
        
        total_masters = sum(1 for u in uids if cache_avg_mmr[u] >= 2800)
        top_peak_uids = sorted(uids, key=lambda uid: cache_peak_mmr.get(uid, 0), reverse=True)
        top3_peak_uids = set(top_peak_uids[:3])
        top4_peak_uids = set(top_peak_uids[:4])
        # General classic queues are calculated by Shared LoL Core. Keep the
        # legacy search below for special modes without running it twice.
        lineup_deadline = time.monotonic() - 1.0 if (shared_lineup or shared_lineup_failed) else time.monotonic() + 6.0
        lineup_timed_out = False
    
        def calculate_stack_penalty(blue_assignment, red_assignment, blue_effs, red_effs):
            blue_set = set(blue_assignment)
            penalty = 0
    
            top4_blue = sum(1 for uid in top4_peak_uids if uid in blue_set)
            top4_red = len(top4_peak_uids) - top4_blue
            top4_gap = abs(top4_blue - top4_red)
            if top4_gap >= 2:
                penalty += 900 * top4_gap
    
            lane_winners = {}
            high_value_winners = {}
            for idx, role in enumerate(ROLES):
                blue_uid = blue_assignment[idx]
                red_uid = red_assignment[idx]
                blue_raw = cache_role_mmr[blue_uid].get(role, 0)
                red_raw = cache_role_mmr[red_uid].get(role, 0)
                raw_gap = blue_raw - red_raw
                eff_gap = blue_effs[idx] - red_effs[idx]
                lane_avg = (blue_raw + red_raw) / 2
                if raw_gap >= LANE_ADVANTAGE_THRESHOLD or eff_gap >= LANE_ADVANTAGE_THRESHOLD:
                    lane_winners[role] = "blue"
                elif raw_gap <= -LANE_ADVANTAGE_THRESHOLD or eff_gap <= -LANE_ADVANTAGE_THRESHOLD:
                    lane_winners[role] = "red"
                else:
                    lane_winners[role] = None
                high_value_winners[role] = (
                    lane_winners[role]
                    if lane_winners[role] and lane_avg >= HIGH_VALUE_LANE_AVG_THRESHOLD
                    else None
                )
    
            blue_lane_wins = sum(1 for team in lane_winners.values() if team == "blue")
            red_lane_wins = sum(1 for team in lane_winners.values() if team == "red")
            lane_stack = max(blue_lane_wins, red_lane_wins)
            if lane_stack >= 4:
                penalty += 1100 * (lane_stack - 3)
    
            for key_roles, stack_cost in (
                (("탑", "미드", "서폿"), 1600),
                (("정글", "미드", "서폿"), 1300),
                (("미드", "원딜", "서폿"), 1100),
            ):
                teams = [lane_winners.get(role) for role in key_roles]
                if teams[0] and teams.count(teams[0]) == len(teams):
                    penalty += stack_cost
    
            core_roles = ("정글", "미드", "서폿")
            core_blue = sum(1 for role in core_roles if lane_winners.get(role) == "blue")
            core_red = sum(1 for role in core_roles if lane_winners.get(role) == "red")
            if max(core_blue, core_red) >= 2 and abs(core_blue - core_red) >= 2:
                penalty += 650 * abs(core_blue - core_red)
    
            high_value_blue = sum(1 for team in high_value_winners.values() if team == "blue")
            high_value_red = sum(1 for team in high_value_winners.values() if team == "red")
            high_value_gap = abs(high_value_blue - high_value_red)
            if high_value_gap >= 2:
                penalty += 650 * (high_value_gap - 1)
    
            bot_lane_winners = [lane_winners.get(role) for role in ("원딜", "서폿")]
            if bot_lane_winners[0] and bot_lane_winners[0] == bot_lane_winners[1]:
                penalty += 450
                if any(high_value_winners.get(role) == bot_lane_winners[0] for role in ("원딜", "서폿")):
                    penalty += 450
    
            jungle_winner = lane_winners.get("정글")
            if jungle_winner:
                other_team = "red" if jungle_winner == "blue" else "blue"
                jungle_team_high_lanes = sum(
                    1 for role in ("탑", "미드", "원딜", "서폿")
                    if high_value_winners.get(role) == jungle_winner
                )
                other_team_high_lanes = sum(
                    1 for role in ("탑", "미드", "원딜", "서폿")
                    if high_value_winners.get(role) == other_team
                )
                if jungle_team_high_lanes == 0 and other_team_high_lanes > 0:
                    penalty += 900
    
            bot_gap = abs((blue_effs[3] + blue_effs[4]) - (red_effs[3] + red_effs[4]))
            bot_gap_limit = get_bot_duo_exclusion_gap(gid)
            if bot_gap >= bot_gap_limit:
                penalty += (bot_gap - (bot_gap_limit - 100)) * 6.0
    
            raw_scores_blue = [cache_role_mmr[blue_assignment[i]].get(ROLES[i], 0) for i in range(5)]
            raw_scores_red = [cache_role_mmr[red_assignment[i]].get(ROLES[i], 0) for i in range(5)]
            raw_support_gap = raw_scores_blue[4] - raw_scores_red[4]
            raw_support_limit = get_support_gap_limit(raw_scores_blue, raw_scores_red, gid)
            if abs(raw_support_gap) >= raw_support_limit:
                support_weak_team = "blue" if raw_support_gap < 0 else "red"
                other_lane_advantages = 0
                for idx, role in enumerate(("탑", "정글", "미드")):
                    role_index = ROLES.index(role)
                    raw_gap = raw_scores_blue[role_index] - raw_scores_red[role_index]
                    if support_weak_team == "blue" and raw_gap >= LANE_ADVANTAGE_THRESHOLD:
                        other_lane_advantages += 1
                    elif support_weak_team == "red" and raw_gap <= -LANE_ADVANTAGE_THRESHOLD:
                        other_lane_advantages += 1
    
                penalty += (abs(raw_support_gap) - raw_support_limit + 120) * 4.0
                if other_lane_advantages == 0:
                    penalty += 900
                elif other_lane_advantages == 1:
                    penalty += 300
    
            return penalty
    
        def is_three_two_primary_match(blue_scores, red_scores):
            lane_results = [get_lane_result(blue_scores[i], red_scores[i]) for i in range(5)]
            blue_wins = lane_results.count("blue")
            red_wins = lane_results.count("red")
            primary_team = get_primary_team(blue_scores, red_scores)
    
            if not ((blue_wins == 2 and red_wins == 3) or (blue_wins == 3 and red_wins == 2)):
                return False
            if blue_wins == 3 and primary_team == "blue":
                return True
            if red_wins == 3 and primary_team == "red":
                return True
            return False
    
        # 조합 최적화 시뮬레이션 엔진 
        for blue_uids in itertools.combinations(uids, 5):
            if time.monotonic() > lineup_deadline:
                lineup_timed_out = True
                break
            red_uids = [u for u in uids if u not in blue_uids]
            if team_violates_separation(gid, blue_uids) or team_violates_separation(gid, red_uids):
                continue
            # 📌 [규칙 1] 마스터 이상 분산 배치 검증
            master_blue = sum(1 for u in blue_uids if cache_avg_mmr[u] >= 2800)
            master_red = total_masters - master_blue
            if abs(master_blue - master_red) > 1:
                continue
            top3_blue = sum(1 for u in top3_peak_uids if u in blue_uids)
            if top3_blue in (0, 3):
                continue
                
            valid_blue_perms = get_valid_permutations(blue_uids)
            if not valid_blue_perms: continue
            
            valid_red_perms = get_valid_permutations(red_uids)
            if not valid_red_perms: continue
            
            for blue_assignment in valid_blue_perms:
                if time.monotonic() > lineup_deadline:
                    lineup_timed_out = True
                    break
                blue_effs = [cache_eff[uid][ROLES[i]] for i, uid in enumerate(blue_assignment)]
                blue_total = sum(blue_effs)
                blue_pref_sum = sum(cache_pref[uid][ROLES[i]] for i, uid in enumerate(blue_assignment))
                
                for red_assignment in valid_red_perms:
                    if time.monotonic() > lineup_deadline:
                        lineup_timed_out = True
                        break
                    red_effs = [cache_eff[uid][ROLES[i]] for i, uid in enumerate(red_assignment)]
                    red_total = sum(red_effs)
                    red_pref_sum = sum(cache_pref[uid][ROLES[i]] for i, uid in enumerate(red_assignment))
                    blue_raws = [cache_role_mmr[uid][ROLES[i]] for i, uid in enumerate(blue_assignment)]
                    red_raws = [cache_role_mmr[uid][ROLES[i]] for i, uid in enumerate(red_assignment)]
    
    # 📌 [4단계: 규칙 이식] Validator 필터 적용
                    b_bot = blue_effs[3] + blue_effs[4] # 원딜+서폿 합계
                    r_bot = red_effs[3] + red_effs[4]   # 원딜+서폿 합계
    
                    blue_synergy_bonus, red_synergy_bonus = get_lineup_synergy_bonuses(blue_raws, red_raws)
                    diff = abs(
                        (blue_total + blue_synergy_bonus)
                        - (red_total + red_synergy_bonus)
                    )
                    total_pref = blue_pref_sum + red_pref_sum
                    lane_diff_sum = sum(abs(blue_effs[i] - red_effs[i]) for i in range(5))
                    stack_penalty = calculate_stack_penalty(blue_assignment, red_assignment, blue_effs, red_effs)
                    fitness = (total_pref * 150) - diff - (lane_diff_sum * 5.0) - stack_penalty
    
                    if fitness > best_fitness_relaxed:
                        best_fitness_relaxed = fitness
                        best_match_relaxed = {
                            "blue": list(blue_assignment),
                            "red": list(red_assignment),
                            "diff": diff,
                            "blue_total": blue_total,
                            "red_total": red_total
                        }
    
                    if (
                        validate_team_safety(blue_effs, red_effs, gid)
                        and validate_team(blue_raws, red_raws, gid=gid)
                        and is_three_two_primary_match(blue_raws, red_raws)
                    ):
                        blue_display_synergy, red_display_synergy = blue_synergy_bonus, red_synergy_bonus
                        display_diff = abs(
                            (sum(blue_raws) + blue_display_synergy)
                            - (sum(red_raws) + red_display_synergy)
                        )
                        display_lane_diff_sum = sum(abs(blue_raws[i] - red_raws[i]) for i in range(5))
                        display_fitness = (total_pref * 150) - display_diff - (display_lane_diff_sum * 5.0) - stack_penalty
                        if display_fitness > best_fitness_display_strict:
                            best_fitness_display_strict = display_fitness
                            best_match_display_strict = {
                                "blue": list(blue_assignment),
                                "red": list(red_assignment),
                                "diff": display_diff,
                                "blue_total": sum(blue_raws),
                                "red_total": sum(red_raws)
                            }
                    
                    # validate_team 규칙에 맞지 않으면 즉시 다음 조합으로 건너뜀
                    if not validate_team_safety(blue_raws, red_raws, gid):
                        continue
                    if not validate_team(blue_effs, red_effs, b_bot, r_bot, gid=gid):
                        continue
                    
                    diff = abs(
                        (blue_total + blue_synergy_bonus)
                        - (red_total + red_synergy_bonus)
                    )
                    total_pref = blue_pref_sum + red_pref_sum
                    # 맞라인 티어 격차 계산
                    lane_diff_sum = sum(abs(blue_effs[i] - red_effs[i]) for i in range(5))
                    
                    # 피트니스 로직: 지망 라인 만족도 극대화 + 맞라인 밸런싱 차이 최소화
                    stack_penalty = calculate_stack_penalty(blue_assignment, red_assignment, blue_effs, red_effs)
                    fitness = (total_pref * 150) - diff - (lane_diff_sum * 5.0) - stack_penalty
                    
                    if fitness > best_fitness_fallback:
                        best_fitness_fallback = fitness
                        best_match_fallback = {
                            "blue": list(blue_assignment),
                            "red": list(red_assignment),
                            "diff": diff,
                            "blue_total": blue_total,
                            "red_total": red_total
                        }
                    
                    # 📌 [규칙 2] 이기는 라인 비중 2:3 및 바텀 점수 합산 스왑 통제 연산
                    if is_three_two_primary_match(blue_effs, red_effs):
                        if fitness > best_fitness_strict:
                            best_fitness_strict = fitness
                            best_match_strict = {
                                "blue": list(blue_assignment),
                                "red": list(red_assignment),
                                "diff": diff,
                                "blue_total": blue_total,
                                "red_total": red_total
                            }
                if lineup_timed_out:
                    break
    
        # 규칙 2번(2:3)을 우선 적용하되, 불가 시 일반 검증 통과안, 그마저 불가 시 최선의 균형안을 사용
        if shared_lineup:
            best_match = {
                "blue": [player.user_id for player in shared_lineup.blue],
                "red": [player.user_id for player in shared_lineup.red],
                "diff": abs(shared_lineup.team_avg_diff),
                "blue_total": sum(player.effective_mmr for player in shared_lineup.blue),
                "red_total": sum(player.effective_mmr for player in shared_lineup.red),
            }
            is_relaxed_match = shared_lineup.relaxed
        else:
            best_match = best_match_display_strict if best_match_display_strict else best_match_strict if best_match_strict else best_match_fallback
            is_relaxed_match = False
            if not best_match and best_match_relaxed:
                best_match = best_match_relaxed
                is_relaxed_match = True
    
        if not best_match:
            msg = (
                "⚠️ **매칭 안내**\n"
                "현재 신청된 포지션 구성만으로는 팀을 만들 수 없습니다.\n"
                "일부 유저가 신청 가능한 포지션을 조금 더 넓히면 매칭이 원활해질 수 있습니다."
            )
            if not interaction.response.is_done(): 
                return await interaction.response.send_message(msg)
            return await interaction.followup.send(msg)
    
        if shared_lineup is None and random.random() < 0.5:
            best_match["blue"], best_match["red"] = best_match["red"], best_match["blue"]
            best_match["blue_total"], best_match["red_total"] = best_match["red_total"], best_match["blue_total"]
    
        def build_role_suggestions():
            suggestions = []
            for uid in uids:
                prefs = user_prefs[uid]
                if not get_requested_roles(*prefs):
                    continue
    
                requested_roles = set(get_requested_roles(*prefs))
                raw_info = bot.user_data.get(gid, {}).get(uid, {})
                ud = ensure_user_format(raw_info)
                extra_roles = [
                    (role, score)
                    for role, score in ud.get('mmr', {}).items()
                    if score > 0 and role not in requested_roles
                ]
                if not extra_roles:
                    continue
    
                extra_roles.sort(key=lambda item: item[1], reverse=True)
                user = uid_to_pdata[uid][0]
                role_text = "/".join(role for role, _ in extra_roles[:2])
                suggestions.append(f"{user.display_name}님은 다음 신청 때 `{role_text}`도 열어두면 매칭 폭이 넓어집니다.")
    
                if len(suggestions) >= 3:
                    break
            return suggestions
    
        def build_lane_gap_advisories(blue_team, red_team):
            advisories = []
            blue_scores = [int(blue_team[i][3] or 0) for i in range(len(ROLES))]
            red_scores = [int(red_team[i][3] or 0) for i in range(len(ROLES))]
            for i, role in enumerate(ROLES):
                blue_user, _, _, blue_mmr = blue_team[i]
                red_user, _, _, red_mmr = red_team[i]
                gap = abs(int(blue_mmr or 0) - int(red_mmr or 0))
                gap_limit = get_lane_exclusion_limit(role, blue_scores, red_scores, gid)
                # MMR 2.0 기준 라인 격차 안내. 실제 제외선과 안내 문구를 분리해
                # 1000점대 초반을 곧바로 "제외급"으로 표현하지 않습니다.
                lane_gap_warning = 700
                lane_gap_very_large = 1000
                if gap < lane_gap_warning:
                    continue
                if gap >= gap_limit:
                    gap_label = "제외급 격차"
                elif gap >= lane_gap_very_large:
                    gap_label = "매우 큰 격차"
                else:
                    gap_label = "큰 격차"
    
                low_mmr = min(int(blue_mmr or 0), int(red_mmr or 0))
                high_mmr = max(int(blue_mmr or 0), int(red_mmr or 0))
                candidate_scores = []
                candidate_names = []
    
                for uid in uids:
                    prefs = user_prefs.get(uid, (None, None, None))
                    requested = set(get_requested_roles(*prefs))
                    if not requested or role in requested:
                        continue
    
                    raw_info = bot.user_data.get(gid, {}).get(uid, {})
                    user_info = ensure_user_format(raw_info)
                    candidate_score = get_noban_queue_score(user_info, role) if q_num == NOBAN_QUEUE_NUM else int(user_info.get('mmr', {}).get(role, 0) or 0)
                    if candidate_score <= 0 or not (low_mmr < candidate_score < high_mmr):
                        continue
                    candidate_scores.append(candidate_score)
                    user = uid_to_pdata[uid][0]
                    candidate_names.append(f"{user.display_name}님")
    
                if candidate_names:
                    shown_candidates = ", ".join(candidate_names[:2])
                    suffix = " 등이" if len(candidate_names) > 2 else "이" if len(candidate_names) == 1 else "들이"
                    suggestion = f"{shown_candidates}{suffix} 다음 신청 때 **{role}**도 열어주면 매칭 폭이 넓어지고 맞라인 격차를 줄이는 데 도움이 됩니다."
                elif candidate_scores:
                    rounded_low = (min(candidate_scores) // 100) * 100
                    rounded_high = ((max(candidate_scores) + 99) // 100) * 100
                    if rounded_low == rounded_high:
                        range_text = f"{rounded_low}점대"
                    else:
                        range_text = f"{rounded_low}~{rounded_high}점대"
                    suggestion = f"{role} MMR {range_text} 유저분들이 다음 신청 때 **{role}**도 열어두면 매칭 폭이 넓어지고 맞라인 격차를 줄이는 데 도움이 됩니다."
                else:
                    suggestion = f"현재 신청자 풀에서는 {role} 라인 중간 점수대 후보가 부족해 완전한 맞라인 균형이 어려울 수 있습니다."
    
                advisories.append(
                    f"**{role}** 라인은 {gap_label}입니다.\n"
                    f"원본 점수차 **{gap}점**\n"
                    f"현재 신청 포지션 조합상 {role}에서 실제로 느끼는 체감 차이가 클 수 있습니다.\n"
                    f"└ {suggestion}"
                )
    
                if len(advisories) >= 2:
                    break
            if len(advisories) < 2 and len(blue_scores) >= 5 and len(red_scores) >= 5:
                bot_gap = get_bot_duo_gap(blue_scores, red_scores)
                if bot_gap >= get_bot_duo_exclusion_gap(gid):
                    blue_bot = blue_scores[3] + blue_scores[4]
                    red_bot = red_scores[3] + red_scores[4]
                    weaker_team = "BLUE" if blue_bot < red_bot else "RED"
                    advisories.append(
                        f"**봇듀오**는 제외급 격차입니다.\n"
                        f"원딜/서폿 합산 차이 **{bot_gap}점**\n"
                        f"바텀에서 실제로 느끼는 체감 차이가 클 수 있습니다.\n"
                        f"└ {weaker_team} 팀이 크게 이기는 탑/정글/미드 쪽을 이용해 바텀 격차를 좁히는 방향을 권장합니다."
                    )
            return advisories
    
        blue_team = []
        role_mapping = {}
        for i, uid in enumerate(best_match["blue"]):
            p_data = uid_to_pdata[uid]
            role = ROLES[i]
            eff_mmr = int(cache_eff[uid][role])
            
            # [변경점] 원본 MMR 추출 (디스코드 출력용)
            raw_info = bot.user_data.get(gid, {}).get(uid, {})
            ud = ensure_user_format(raw_info)
            orig_mmr = get_noban_queue_score(ud, role) if q_num == NOBAN_QUEUE_NUM else ud['mmr'].get(role, 0)
                
            blue_team.append((p_data[0], role, eff_mmr, orig_mmr))
            role_mapping[uid] = role
            
        red_team = []
        for i, uid in enumerate(best_match["red"]):
            p_data = uid_to_pdata[uid]
            role = ROLES[i]
            eff_mmr = int(cache_eff[uid][role])
            
            # [변경점] 원본 MMR 추출 (디스코드 출력용)
            raw_info = bot.user_data.get(gid, {}).get(uid, {})
            ud = ensure_user_format(raw_info)
            orig_mmr = get_noban_queue_score(ud, role) if q_num == NOBAN_QUEUE_NUM else ud['mmr'].get(role, 0)
                
            red_team.append((p_data[0], role, eff_mmr, orig_mmr))
            role_mapping[uid] = role
    
        if gid not in bot.active_games: 
            bot.active_games[gid] = {}
            
        bot.active_games[gid][q_num] = initialize_active_game_state(gid, q_num, {
            'mode': NOBAN_MODE_KEY if q_num == NOBAN_QUEUE_NUM else LOW_TIER_MODE_KEY if q_num == LOW_TIER_QUEUE_KEY else "classic",
            'roles': role_mapping,
            'rating_sources': {
                uid: get_noban_rating_source(
                    ensure_user_format(bot.user_data.get(gid, {}).get(uid, {})),
                    role_mapping.get(uid)
                )
                for uid in role_mapping
            } if q_num == NOBAN_QUEUE_NUM else {},
            'requested_prefs': {uid: list(prefs) for uid, prefs in user_prefs.items()},
            'low_tier_forced_ids': [
                uid for uid, p_data in uid_to_pdata.items()
                if q_num == LOW_TIER_QUEUE_KEY and is_low_tier_force_entry(p_data)
            ],
            'lineup_mmr': {
                str(user.id): int(orig_mmr)
                for user, _, _, orig_mmr in blue_team + red_team
            },
            'blue': [str(u.id) for u, _, _, _ in blue_team],
            'red': [str(u.id) for u, _, _, _ in red_team]
        })
        await check_queue_lineup_titles(interaction, gid, q_num, q[:10])
    
        # ----------------------------------------------------
        # [음성 인프라 구축 및 시각화 게이지 바 연산 부문]
        # ----------------------------------------------------
        guild = interaction.guild
        blue_channel_name, red_channel_name = get_classic_voice_channel_names(q_num)
        game_state = bot.active_games[gid][q_num]
        classic_game = game_state.get("mode") == "classic"
        voice_create_kwargs = {"include_waiting": True} if classic_game else {}
        _persist_active_game(gid, game_state)
        await create_and_move_team_voice_channels(
            guild,
            [
                (blue_channel_name, [u for u, _, _, _ in blue_team]),
                (red_channel_name, [u for u, _, _, _ in red_team]),
            ],
            game_state=game_state,
            **voice_create_kwargs,
        )
    
        # 내부 매칭은 가중치 적용 MMR을 쓰지만, 유저에게 보이는 전력 분석은 원본 MMR 총점 기준으로 표시합니다.
        blue_total_eff = sum(item[2] for item in blue_team)
        red_total_eff = sum(item[2] for item in red_team)
        internal_diff = blue_total_eff - red_total_eff
        
        # 텍스트로 보여지는 팀 총합 및 평균 점수는 가중치가 빠진 원본 MMR(orig_mmr, item[3])을 기준으로 합산합니다.
        blue_display_total = sum(item[3] for item in blue_team)
        blue_avg = int(blue_display_total / 5) if blue_team else 0
        red_display_total = sum(item[3] for item in red_team)
        red_avg = int(red_display_total / 5) if red_team else 0
        diff = blue_display_total - red_display_total
        avg_diff = blue_avg - red_avg
        
        if abs(avg_diff) <= 50:
            gauge_str = "🔹 [█████⚖️█████] 🔹\n✨ 분석 결과: 완벽한 매치업! ✨"
        elif avg_diff > 0:
            if avg_diff > 360:
                gauge_str = "🔵 [████████░░] 🔴\n⚠️ 전력 경고: 블루팀이 뚜렷하게 우세합니다."
            elif avg_diff > 160:
                gauge_str = "🔵 [███████░░░] 🔴\n⚖️ 전력 분석: 블루팀이 우세하지만 플레이로 뒤집을 수 있는 차이입니다."
            else:
                gauge_str = "🔵 [██████░░░░] 🔴\n⚖️ 전력 분석: 블루팀이 살짝 앞서지만 적당한 차이입니다."
        else:
            if avg_diff < -360:
                gauge_str = "🔵 [░░████████] 🔴\n⚠️ 전력 경고: 레드팀이 뚜렷하게 우세합니다."
            elif avg_diff < -160:
                gauge_str = "🔵 [░░░███████] 🔴\n⚖️ 전력 분석: 레드팀이 우세하지만 플레이로 뒤집을 수 있는 차이입니다."
            else:
                gauge_str = "🔵 [░░░░██████] 🔴\n⚖️ 전력 분석: 레드팀이 살짝 앞서지만 적당한 차이입니다."
    
        lane_gap_advisories = build_lane_gap_advisories(blue_team, red_team)
    
        if abs(avg_diff) > 360:
            gauge_str += f"\n\n🚨 **[AI 밸런스 경고]** 🚨\n팀 평균 격차가 **{abs(avg_diff)}점**으로 크게 벌어져 있습니다.\n"
            
            worst_pos = None
            max_gap = 0
            for i, pos in enumerate(ROLES):
                b_display = blue_team[i][3]
                r_display = red_team[i][3]
                gap = abs(b_display - r_display)
                if gap > max_gap:
                    max_gap = gap
                    worst_pos = pos
                    
            gauge_str += f"\n💡 **포지션 조정 추천**\n"
            gauge_str += f"- 가장 큰 라인 격차: **{worst_pos} {max_gap}점**\n"
            gauge_str += f"- **{worst_pos}** 라인 점수대가 한쪽으로 몰려 있습니다.\n"
            if lane_gap_advisories:
                gauge_str += f"- 아래 `라인별 전력 격차 안내`에 표시되는 유저가 다음 신청 때 **{worst_pos}**도 열어주면 매칭 폭이 넓어집니다."
            else:
                gauge_str += f"- 현재 신청자 풀에서는 **{worst_pos}** 중간 점수대 후보가 부족해 재라인업을 검토하는 편이 좋습니다."
    
        if lane_gap_advisories:
            gauge_str += "\n\n⚠️ **[라인별 전력 격차 안내]**\n"
            gauge_str += "\n".join(f"- {line}" for line in lane_gap_advisories)
    
        if is_relaxed_match:
            suggestion_lines = build_role_suggestions()
            if suggestion_lines:
                gauge_str += "\n\n💡 **다음 매칭 추천**\n" + "\n".join(f"- {line}" for line in suggestion_lines)
    
        embed_summary = discord.Embed(
            title=f"⚔️ {LOW_TIER_MODE_NAME} 매치 라인업" if q_num == LOW_TIER_QUEUE_KEY else f"⚔️ {get_queue_label(q_num)} 큐 매치 라인업",
            description=f"**📊 양 팀 전력 비교**\n{gauge_str}",
            color=0x2b2d31
        )
        embed_summary.add_field(name="🔵 BLUE 평균", value=f"**{get_public_mmr_rank(blue_avg)}**", inline=True)
        embed_summary.add_field(name="🔴 RED 평균", value=f"**{get_public_mmr_rank(red_avg)}**", inline=True)
    
        # 상단 카드와 항상 함께 전송되므로 두 번째 카드의 중복 제목은 생략한다.
        embed_lineup = discord.Embed(color=0x2b2d31)
        blue_lines = []
        # [변경점] 포지션 출력 시 가중치가 곱해진 eff_mmr 대신 순수 orig_mmr 표출
        for user, role, eff_mmr, orig_mmr in blue_team:
            u_info_raw = bot.user_data.get(gid, {}).get(str(user.id), {'mmr': 0})
            user_info = ensure_user_format(u_info_raw)
            t_name = get_tier_name(orig_mmr)
            blue_lines.append(format_lineup_player_line(role, user, user_info, get_tier_emoji(t_name, interaction.guild, gid), orig_mmr))
    
        red_lines = []
        # [변경점] 동일하게 orig_mmr 표출
        for user, role, eff_mmr, orig_mmr in red_team:
            u_info_raw = bot.user_data.get(gid, {}).get(str(user.id), {'mmr': 0})
            user_info = ensure_user_format(u_info_raw)
            t_name = get_tier_name(orig_mmr)
            red_lines.append(format_lineup_player_line(role, user, user_info, get_tier_emoji(t_name, interaction.guild, gid), orig_mmr))
    
        matchup_lines = []
        for i, role in enumerate(ROLES):
            _, _, _, blue_mmr = blue_team[i]
            _, _, _, red_mmr = red_team[i]
            gap = blue_mmr - red_mmr
    
            gap_text = format_lineup_gap_text(gap)
    
            matchup_lines.append(f"{get_role_display_marker(role, interaction.guild)} {gap_text}")
    
        if avg_diff == 0:
            team_gap_text = "⚪ 팀 평균 동률"
        elif avg_diff > 0:
            team_gap_text = f"🔵 BLUE TEAM +{avg_diff}"
        else:
            team_gap_text = f"🔴 RED TEAM +{abs(avg_diff)}"
    
        apply_classic_lineup_embed(
            embed_lineup,
            interaction.guild,
            gid,
            blue_team,
            red_team,
            blue_avg,
            red_avg,
            team_gap_text,
        )
    
        quality_matchups = []
        for i, role in enumerate(ROLES):
            blue_user, _, _, blue_mmr = blue_team[i]
            red_user, _, _, red_mmr = red_team[i]
            quality_matchups.append({
                "role": role,
                "blue_label": blue_user.mention,
                "red_label": red_user.mention,
                "blue_mmr": blue_mmr,
                "red_mmr": red_mmr,
            })
    
        warning_text = build_match_quality_warning(quality_matchups, gid)
        if warning_text:
            embed_lineup.add_field(name="🚨 매칭 품질 안내", value=warning_text, inline=False)
    
        rival_entries = get_directed_rival_match_entries(
            gid,
            [str(user.id) for user, _, _, _ in blue_team],
            [str(user.id) for user, _, _, _ in red_team],
        )
        rival_lines = format_rival_matchup_lines(interaction.guild, gid, rival_entries)
    
        await send_match_output(interaction, gid, embeds=[embed_summary, embed_lineup])
        await send_chzzk_lineup_summary(gid, q_num, blue_team, red_team)
        dm_failed = await send_classic_lineup_dm_notifications(
            gid,
            q_num,
            blue_team,
            red_team,
            [embed_summary, embed_lineup],
        )
        if dm_failed:
            await send_match_output(
                interaction,
                gid,
                content="📭 DM 발송 실패: " + ", ".join(dm_failed[:10]),
                allowed_mentions=discord.AllowedMentions.none(),
                notify=False,
            )
        if rival_lines:
            await send_match_output(
                interaction,
                gid,
                content="🔥 **라이벌 매치 성사!**\n" + "\n".join(rival_lines[:6]),
                allowed_mentions=discord.AllowedMentions.none(),
                notify=False,
            )
    
    async def cleanup_vcs(guild, q_num, game_state=None):
        category = await get_or_create_match_category(guild)
        if not category:
            logger.warning("팀 음성 채널 정리 실패: 내전 카테고리 없음 guild_id=%s", getattr(guild, "id", None))
            return

        persisted_voice_channels = game_state.get("voice_channels", {}) if isinstance(game_state, dict) else {}
        if not isinstance(persisted_voice_channels, dict):
            persisted_voice_channels = {}
        waiting_vc = None
        waiting_channel_id = persisted_voice_channels.get("waiting")
        if waiting_channel_id is not None and hasattr(guild, "get_channel"):
            try:
                waiting_vc = guild.get_channel(int(waiting_channel_id))
            except (TypeError, ValueError):
                waiting_vc = None
        waiting_vc = waiting_vc or discord.utils.get(category.voice_channels, name="내전 대기실")
        if not waiting_vc:
            waiting_vc = discord.utils.get(guild.voice_channels, name="내전 대기실")
        if not waiting_vc:
            try:
                waiting_vc = await guild.create_voice_channel("내전 대기실", category=category)
            except Exception as exc:
                logger.warning("내전 대기실 생성 실패: %s", exc)
                waiting_vc = None

        queue_label = get_queue_label(q_num)
        blue_channel_name, red_channel_name = get_classic_voice_channel_names(q_num)
        names_to_delete = {
            blue_channel_name,
            red_channel_name,
            f"🔵 큐 {queue_label} - 블루팀",
            f"🔴 큐 {queue_label} - 레드팀",
        }

        if q_num == ARENA_QUEUE_NUM:
            names_to_delete.update(f"🏟️ 아레나 팀 {idx}" for idx in range(1, ARENA_TEAM_COUNT + 1))
        elif q_num == LEAGUE_QUEUE_KEY:
            names_to_delete.update(f"🏆 {LEAGUE_MODE_NAME} {idx}팀" for idx in range(1, LEAGUE_TEAM_COUNT + 1))
        elif q_num == LEAGUE_SERIES_QUEUE_KEY:
            names_to_delete.update(f"🏆 {LEAGUE_SERIES_MODE_NAME} {idx}팀" for idx in range(1, LEAGUE_SERIES_MAX_TEAM_COUNT + 1))
        elif q_num == ARAM_LEAGUE_QUEUE_KEY:
            names_to_delete.update(f"❄️ {ARAM_LEAGUE_MODE_NAME} {idx}팀" for idx in range(1, ARAM_LEAGUE_MAX_TEAM_COUNT + 1))

        deleted = 0
        failed = 0

        target_channels = []
        target_ids = set()
        missing_persisted_channel = False
        for channel_id in persisted_voice_channels.values():
            try:
                vc = guild.get_channel(int(channel_id)) if hasattr(guild, "get_channel") else None
            except (TypeError, ValueError):
                vc = None
            if vc is None:
                missing_persisted_channel = True
                continue
            if getattr(vc, "id", None) == getattr(waiting_vc, "id", None):
                continue
            target_ids.add(getattr(vc, "id", None))
            target_channels.append(vc)
        if not target_ids or missing_persisted_channel:
            for vc in list(category.voice_channels):
                if getattr(vc, "name", None) not in names_to_delete:
                    continue
                if getattr(vc, "id", None) == getattr(waiting_vc, "id", None):
                    continue
                if getattr(vc, "id", None) in target_ids:
                    continue
                target_ids.add(getattr(vc, "id", None))
                target_channels.append(vc)

        for vc in target_channels:

            if waiting_vc:
                for member in list(vc.members):
                    if not await move_member_to_voice_verified(member, waiting_vc, reason="내전 경기 종료"):
                        logger.warning(
                            "팀방 잔여 인원 이동 실패: channel_id=%s user_id=%s",
                            getattr(vc, "id", None),
                            getattr(member, "id", None),
                        )

            try:
                await vc.delete(reason="내전 경기 종료")
                deleted += 1
            except Exception as exc:
                failed += 1
                logger.warning(
                    "팀 음성 채널 삭제 실패: guild_id=%s channel_id=%s name=%s error=%s",
                    getattr(guild, "id", None),
                    getattr(vc, "id", None),
                    vc.name,
                    exc,
                )

        logger.info(
            "경기 종료 팀 음성 채널 정리 결과: guild_id=%s queue=%s deleted=%s failed=%s",
            getattr(guild, "id", None),
            q_num,
            deleted,
            failed,
        )

    # ==============================================================================
    # [4. 내전 관리자 제어 명령어 파트]
    # ==============================================================================
    
    
    @bot.tree.command(name="승리", description="[내전 관리자] 결과를 기록합니다. 리그전은 매치번호를 함께 입력합니다.")
    @app_commands.choices(대상=win_target_choices)
    @app_commands.describe(
        대상="결과를 기록할 큐입니다.",
        매치번호="리그전 전용입니다. 대진표의 매치번호를 입력합니다.",
        승리팀="일반/아레나/총력전은 이 칸에 승리팀을 입력하면 됩니다.",
        큐유지="일반 내전 큐에서만 사용합니다. 결과 기록 후 큐를 유지합니다."
    )
    async def win_record(interaction: discord.Interaction, 대상: str, 매치번호: str = None, 승리팀: str = None, 큐유지: bool = False):
        # 일반 슬래시 명령은 기존처럼 관리자 전용입니다.
        # ROFL 승패 기록 패널은 참가자 검증을 끝낸 내부 호출만 이 검사를 우회합니다.
        if not getattr(interaction, "_lucid_internal_match_record", False) and not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        queue_key = normalize_queue_selector(대상)
        if queue_key is None:
            return await interaction.response.send_message(f"⚠️ 큐는 `1~5`, `노밴 모드`, `저티어 큐`, `아레나(3x6)`, `협곡 리그전`, `칼바람 나락`, `칼바람 리그전` 중에서 선택해주세요.", ephemeral=True)
        feature_key = get_queue_feature_key(queue_key)
        if feature_key and not is_feature_enabled(gid, feature_key):
            return await interaction.response.send_message(get_disabled_feature_message(feature_key), ephemeral=True)
    
        process_key = (gid, queue_key)
        if process_key in bot.processing_games:
            return await interaction.response.send_message(
                f"⏳ {get_queue_label(queue_key)} 큐 결과가 이미 처리 중입니다. 잠시만 기다려주세요.",
                ephemeral=True
            )
    
        game_state = bot.active_games.get(gid, {}).get(queue_key)
        
        if not game_state:
            return await interaction.response.send_message(
                f"❌ 해당 {get_queue_label(queue_key)} 큐에는 현재 진행 중인 게임이 확인되지 않습니다.", 
                ephemeral=True
            )
    
        bot.processing_games.add(process_key)
        response_is_done = getattr(interaction.response, "is_done", None)
        if not (callable(response_is_done) and response_is_done()):
            await interaction.response.defer()
        if bot.title_batch is None:
            bot.title_batch = {}
        bot.title_batch[gid] = []
    
        try:
            if game_state.get("mode") == LEAGUE_MODE_KEY:
                if 매치번호 is None or 승리팀 is None:
                    return await interaction.followup.send(f"🏆 {get_queue_label(queue_key)}은 `/승리 {get_queue_label(queue_key)} [매치번호] [승리팀]` 형식으로 입력해주세요.")
                match_no_text = parse_league_match_no(매치번호)
                if not match_no_text:
                    return await interaction.followup.send(f"🏆 {get_queue_label(queue_key)} 매치번호는 `1`, `2`, `3` 중 하나로 입력해주세요.")
                match_no = int(match_no_text)
                return await process_league_win(interaction, gid, match_no, 승리팀, game_state, queue_key=queue_key)
            if game_state.get("mode") in (LEAGUE_SERIES_MODE_KEY, ARAM_LEAGUE_MODE_KEY):
                if 매치번호 is None or 승리팀 is None:
                    return await interaction.followup.send(f"🏆 {get_queue_label(queue_key)}은 `/승리 {get_queue_label(queue_key)} [매치번호] [승리팀]` 형식으로 입력해주세요.")
                match_no_match = re.search(r"\d+", str(매치번호 or ""))
                if not match_no_match:
                    return await interaction.followup.send("🏆 매치번호는 대진표에 표시된 숫자로 입력해주세요.")
                match_no = int(match_no_match.group(0))
                return await process_league_series_win(interaction, gid, match_no, 승리팀, game_state)
    
            winner_text = 승리팀 if 승리팀 is not None else 매치번호
            if winner_text is None:
                return await interaction.followup.send(f"⚠️ {get_queue_label(queue_key)} 결과는 `/승리 {get_queue_label(queue_key)} [승리팀]` 형식으로 입력해주세요.")
            if game_state.get("mode") == EVENT_MODE_KEY:
                return await process_arena_win(interaction, gid, queue_key, winner_text, game_state)
            if game_state.get("mode") == ARAM_MODE_KEY:
                return await process_aram_win(interaction, gid, queue_key, winner_text, game_state)
            await process_classic_win(interaction, gid, queue_key, winner_text, 큐유지, game_state)
        finally:
            try:
                await flush_title_batch(interaction, gid)
            except Exception:
                logger.exception(
                    "경기 결과 후처리 알림 배치 실패: guild_id=%s queue=%s",
                    gid,
                    queue_key,
                )
            bot.processing_games.discard(process_key)
    
    @win_record.autocomplete("매치번호")
    async def win_match_no_autocomplete(interaction: discord.Interaction, current: str):
        target = getattr(interaction.namespace, "대상", None)
        queue_key = normalize_queue_selector(target) if target else None
        if queue_key not in (LEAGUE_QUEUE_KEY, LEAGUE_SIM_QUEUE_KEY, LEAGUE_SERIES_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY):
            return []
    
        gid = str(interaction.guild_id)
        game_state = bot.active_games.get(gid, {}).get(queue_key, {})
        matches = game_state.get("matches", {}) if game_state else {}
        if queue_key in (LEAGUE_SERIES_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY):
            choices = []
            for match_id in game_state.get("match_order", []):
                match = matches.get(str(match_id), {})
                if match.get("winner"):
                    continue
                label = f"매치 {match_id} · {match.get('round_name', '라운드')}"
                if current and current not in str(match_id) and current not in label:
                    continue
                choices.append(app_commands.Choice(name=label[:100], value=str(match_id)))
            return choices[:25]
        choices = []
        for match_no in ("1", "2", "3"):
            match = matches.get(match_no, {})
            if match.get("winner"):
                continue
            if match_no == "3" and not (matches.get("1", {}).get("winner") and matches.get("2", {}).get("winner")):
                continue
            label = "매치 3(결승)" if match_no == "3" else f"매치 {match_no}"
            if current and current not in match_no and current not in label:
                continue
            suffix = " · 시뮬레이션" if queue_key == LEAGUE_SIM_QUEUE_KEY else ""
            choices.append(app_commands.Choice(name=f"{label}{suffix}", value=label))
        return choices[:25]
    
    @win_record.autocomplete("승리팀")
    async def win_team_autocomplete(interaction: discord.Interaction, current: str):
        target = getattr(interaction.namespace, "대상", None)
        queue_key = normalize_queue_selector(target) if target else None
        if queue_key not in (LEAGUE_QUEUE_KEY, LEAGUE_SIM_QUEUE_KEY, LEAGUE_SERIES_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY):
            return []
    
        gid = str(interaction.guild_id)
        game_state = bot.active_games.get(gid, {}).get(queue_key, {})
        matches = game_state.get("matches", {}) if game_state else {}
        match_no = parse_league_match_no(getattr(interaction.namespace, "매치번호", None))
        if queue_key in (LEAGUE_SERIES_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY):
            raw_match_no = getattr(interaction.namespace, "매치번호", None)
            match_id = str(match_no or raw_match_no or "").strip()
            match = matches.get(match_id, {})
            team_nos = get_series_match_team_nos(match, matches) if match else []
            teams_by_no = {int(team.get("team_no")): team for team in game_state.get("teams", [])}
            choices = []
            for team_no in sorted({int(no) for no in team_nos if no}):
                team = teams_by_no.get(team_no, {"team_no": team_no})
                label = format_league_team_name(team)
                if current and current not in str(team_no) and normalize_team_name_key(current) not in normalize_team_name_key(label):
                    continue
                choices.append(app_commands.Choice(name=label[:100], value=label[:100]))
            return choices[:25]
        if match_no == "3" and matches.get("1", {}).get("winner") and matches.get("2", {}).get("winner"):
            team_nos = [matches["1"]["winner"], matches["2"]["winner"]]
        elif match_no:
            team_nos = matches.get(match_no, {}).get("team_nos", [])
        else:
            team_nos = [team.get("team_no") for team in game_state.get("teams", [])]
        choices = []
        suffix = " · 시뮬레이션" if queue_key == LEAGUE_SIM_QUEUE_KEY else ""
        for team_no in sorted({int(no) for no in team_nos if no}):
            label = f"{team_no}팀{suffix}"
            if current and current not in str(team_no) and current not in label:
                continue
            choices.append(app_commands.Choice(name=label, value=f"{team_no}팀"))
        return choices[:25]
    
    @bot.tree.command(name="팀명변경", description="진행 중인 리그전 팀 이름을 변경합니다.")
    @app_commands.describe(팀번호="변경할 팀 번호입니다.", 팀이름="새 팀 이름입니다. 30자 이하")
    async def rename_tournament_team(
        interaction: discord.Interaction,
        팀번호: app_commands.Range[int, 1, LEAGUE_SERIES_MAX_TEAM_COUNT],
        팀이름: str,
    ):
        gid = str(interaction.guild_id)
        active_games = bot.active_games.get(gid, {})
        if active_games.get(LEAGUE_SERIES_QUEUE_KEY):
            queue_key = LEAGUE_SERIES_QUEUE_KEY
        elif active_games.get(ARAM_LEAGUE_QUEUE_KEY):
            queue_key = ARAM_LEAGUE_QUEUE_KEY
        elif active_games.get(LEAGUE_SERIES_SIM_QUEUE_KEY):
            queue_key = LEAGUE_SERIES_SIM_QUEUE_KEY
        else:
            queue_key = LEAGUE_QUEUE_KEY
        game_state = active_games.get(queue_key)
        if not game_state or game_state.get("mode") not in (LEAGUE_MODE_KEY, LEAGUE_SERIES_MODE_KEY, ARAM_LEAGUE_MODE_KEY):
            return await interaction.response.send_message("⚠️ 진행 중인 리그전을 찾지 못했습니다.", ephemeral=True)
        if game_state.get("finalized"):
            return await interaction.response.send_message("⚠️ 이미 종료된 리그전의 팀명은 변경할 수 없습니다.", ephemeral=True)
    
        team_name = " ".join(str(팀이름).strip().split())
        if not team_name:
            return await interaction.response.send_message("⚠️ 팀 이름을 입력해주세요.", ephemeral=True)
        if len(team_name) > 30:
            return await interaction.response.send_message("⚠️ 팀 이름은 30자 이하로 입력해주세요.", ephemeral=True)
    
        teams = game_state.get("teams", [])
        team = next((item for item in teams if int(item.get("team_no", 0) or 0) == int(팀번호)), None)
        if not team:
            return await interaction.response.send_message(f"⚠️ {팀번호}팀을 찾지 못했습니다.", ephemeral=True)
    
        is_member = str(interaction.user.id) in {str(uid) for uid in team.get("players", [])}
        if not is_member and not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 팀 멤버 또는 내전 관리자만 팀명을 변경할 수 있습니다.", ephemeral=True)
    
        await interaction.response.defer(ephemeral=True)
        old_name = format_league_team_name(team)
        team["name"] = team_name
        bot.save_lucid_data(gid)
    
        await interaction.followup.send(f"✅ {old_name} → **{discord.utils.escape_markdown(team_name)}** 팀명 변경 완료", ephemeral=True)
        embed = build_league_series_embed(interaction.guild, gid, game_state, title_suffix="팀명 변경") if queue_key in (LEAGUE_SERIES_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY) else discord.Embed(
            title=f"🏷️ {get_queue_label(queue_key)} 팀명 변경",
            description=f"{old_name} → **{discord.utils.escape_markdown(team_name)}**",
            color=0x3498db,
        )
        send_output = send_league_sim_output if queue_key in (LEAGUE_SIM_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY) else send_league_output
        await send_output(interaction, gid, embed=embed, allowed_mentions=discord.AllowedMentions.none(), notify=False)
    
    async def process_arena_win(interaction, gid, 큐, 승리팀, game_state):
            winner_team_no = parse_arena_winner(승리팀)
            if winner_team_no is None:
                return await interaction.followup.send("🏟️ 아레나(3x6)은 승리팀을 `1`~`6` 또는 `아레나 팀 1`처럼 입력해주세요.")
    
            teams = game_state.get("teams", [])
            winner_team = next((team for team in teams if team.get("team_no") == winner_team_no), None)
            if not winner_team:
                return await interaction.followup.send(f"❌ 아레나 팀 {winner_team_no} 정보를 찾을 수 없습니다.")
    
            bot.user_data.setdefault(gid, {})
            winner_ids = set(winner_team.get("players", []))
            all_ids = [uid for team in teams for uid in team.get("players", [])]
            player_records = []
    
            for uid_str in all_ids:
                member = interaction.guild.get_member(int(uid_str))
                if not member:
                    try:
                        member = await interaction.guild.fetch_member(int(uid_str))
                    except (discord.NotFound, discord.HTTPException):
                        member = None
    
                display_name = member.display_name if member else f"UID {uid_str}"
                if uid_str not in bot.user_data[gid]:
                    bot.user_data[gid][uid_str] = {
                        'mmr': {r:0 for r in ROLES},
                        'plays': {r:0 for r in ROLES},
                        'eval_scores': {r: [] for r in ROLES},
                        'win': 0,
                        'loss': 0,
                        'streak': 0,
                        'lol_name': display_name
                    }
    
                ud = ensure_user_format(bot.user_data[gid][uid_str])
                stats = ud['event_stats'][EVENT_MODE_KEY]
                result = "win" if uid_str in winner_ids else "loss"
                if result == "win":
                    stats['win'] += 1
                else:
                    stats['loss'] += 1
    
                player_records.append({
                    "user_id": uid_str,
                    "name": display_name,
                    "team": next((team.get("name") for team in teams if uid_str in team.get("players", [])), ""),
                    "result": result
                })
    
            await grant_first_team_title(interaction, gid, list(winner_team.get("players", [])), "first_arena_champion")
            for uid_str in winner_ids:
                await check_arena_title_unlocks(interaction, gid, uid_str)
    
            match_id = f"{now_kst().strftime('%Y%m%d%H%M%S')}-arena-q{큐}"
            append_match_history(gid, {
                "id": match_id,
                "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
                "queue": 큐,
                "mode": EVENT_MODE_KEY,
                "winner": f"아레나 팀 {winner_team_no}",
                "teams": teams,
                "players": player_records,
                "cancelled": False
            })
    
            bot.save_lucid_data(gid)
    
            bot.queues[gid][큐] = []
            if 큐 in bot.active_games[gid]:
                del bot.active_games[gid][큐]
            delete_participation_recruitment(gid, 큐)
            set_start_wait_enabled(gid, 큐, False)
            touch_queue(gid, 큐)
            bot.save_lucid_data(gid)
            schedule_participation_panel_refresh(gid, delay=0.2)
    
            embed = discord.Embed(
                title=f"🏟️ {큐}번 큐 {EVENT_MODE_NAME} 결과 기록 완료",
                description=(
                    f"우승: **아레나 팀 {winner_team_no}**\n"
                    "이벤트 전적만 반영했습니다. MMR과 일반 내전 승패는 변경되지 않습니다.\n"
                    "매치 기록 후 대기열 데이터가 초기화되었습니다."
                ),
                color=0xf39c12
            )
            embed.add_field(name="이벤트 전적 반영", value="우승 팀 3명 `승 +1` · 나머지 15명 `패 +1`", inline=False)
            await interaction.followup.send(embed=embed)
            try:
                await cleanup_vcs(interaction.guild, 큐, game_state)
            except Exception as e:
                logger.warning(f"아레나 큐 정리 중 오류: {e}")
            return
    
    async def process_aram_win(interaction, gid, queue_key, winner_text, game_state):
        normalized = str(winner_text).replace("팀", "").strip().lower()
        if normalized in ("1", "blue", "블루", "블루팀"):
            winner = "blue"
            winner_label = "BLUE TEAM"
        elif normalized in ("2", "red", "레드", "레드팀"):
            winner = "red"
            winner_label = "RED TEAM"
        else:
            return await interaction.followup.send("⚔️ 칼바람 나락 승리팀은 `블루`, `레드`, `1`, `2` 중 하나로 입력해주세요.")
    
        bot.user_data.setdefault(gid, {})
        blue_ids = [str(uid) for uid in game_state.get("blue", [])]
        red_ids = [str(uid) for uid in game_state.get("red", [])]
        winner_ids = set(blue_ids if winner == "blue" else red_ids)
        all_ids = blue_ids + red_ids
        player_records = []
    
        for uid_str in all_ids:
            member = interaction.guild.get_member(int(uid_str))
            if not member:
                try:
                    member = await interaction.guild.fetch_member(int(uid_str))
                except (discord.NotFound, discord.HTTPException):
                    member = None
    
            display_name = member.display_name if member else f"UID {uid_str}"
            if uid_str not in bot.user_data[gid]:
                bot.user_data[gid][uid_str] = {
                    'mmr': {r: 0 for r in ROLES},
                    'plays': {r: 0 for r in ROLES},
                    'eval_scores': {r: [] for r in ROLES},
                    'win': 0,
                    'loss': 0,
                    'streak': 0,
                    'lol_name': display_name
                }
    
            user_info = ensure_user_format(bot.user_data[gid][uid_str])
            stats = user_info['event_stats'][ARAM_MODE_KEY]
            result = "win" if uid_str in winner_ids else "loss"
            if result == "win":
                stats['win'] += 1
            else:
                stats['loss'] += 1
    
            player_records.append({
                "user_id": uid_str,
                "name": display_name,
                "team": "blue" if uid_str in blue_ids else "red",
                "result": result,
                "delta": 0
            })
    
        for uid_str in all_ids:
            await check_aram_title_unlocks(interaction, gid, uid_str)
    
        match_id = f"{now_kst().strftime('%Y%m%d%H%M%S')}-aram-q{queue_key}"
        append_match_history(gid, {
            "id": match_id,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            "queue": queue_key,
            "mode": ARAM_MODE_KEY,
            "winner": winner,
            "blue_total": game_state.get("blue_total", 0),
            "red_total": game_state.get("red_total", 0),
            "players": player_records,
            "cancelled": False
        })
    
        bot.queues.setdefault(gid, {})[queue_key] = []
        bot.active_games.setdefault(gid, {}).pop(queue_key, None)
        delete_participation_recruitment(gid, queue_key)
        set_start_wait_enabled(gid, queue_key, False)
        touch_queue(gid, queue_key)
        bot.save_lucid_data(gid)
        schedule_participation_panel_refresh(gid, delay=0.2)
    
        def member_line(uid):
            return get_member_label(interaction.guild, gid, uid)
    
        embed = discord.Embed(
            title=f"⚔️ {ARAM_MODE_NAME} 결과 기록 완료",
            description=(
                f"승리팀: **{winner_label}**\n"
                "이 결과는 총력전 이벤트 전적에만 반영됩니다.\n"
                "**MMR, 일반 내전 승패, 연승 점수는 변경되지 않습니다.**"
            ),
            color=0x1abc9c
        )
        embed.add_field(
            name=f"🔵 BLUE TEAM {'승리' if winner == 'blue' else '패배'} · 총점 {game_state.get('blue_total', 0)}",
            value="\n".join(member_line(uid) for uid in blue_ids) or "기록 없음",
            inline=False
        )
        embed.add_field(
            name=f"🔴 RED TEAM {'승리' if winner == 'red' else '패배'} · 총점 {game_state.get('red_total', 0)}",
            value="\n".join(member_line(uid) for uid in red_ids) or "기록 없음",
            inline=False
        )
        embed.set_footer(text="칼바람 나락은 최고 티어 MMR 기준으로 팀을 나누며, 점수 변동은 없습니다.")
        await send_match_output(interaction, gid, embed=embed)
        try:
            await cleanup_vcs(interaction.guild, queue_key, game_state)
        except Exception as exc:
            logger.warning("칼바람 나락 음성 채널 정리 중 오류: %s", exc)
        return
    
    async def process_league_win(interaction, gid, 매치번호, 승리팀, game_state, queue_key=LEAGUE_QUEUE_KEY):
        is_simulation = bool(game_state.get("simulation")) or queue_key == LEAGUE_SIM_QUEUE_KEY
        if 매치번호 not in (1, 2, 3):
            return await interaction.followup.send(f"🏆 {get_queue_label(queue_key)} 매치번호는 `1`, `2`, `3` 중 하나로 입력해주세요.")
    
        matches = game_state.setdefault("matches", {})
        match = matches.get(str(매치번호))
        if not match:
            return await interaction.followup.send(f"❌ 해당 {get_queue_label(queue_key)} 매치 정보를 찾을 수 없습니다.")
        if match.get("winner"):
            return await interaction.followup.send(f"⚠️ 매치 {매치번호}는 이미 {LEAGUE_MODE_NAME} {match['winner']}팀 승리로 기록되어 있습니다.")
    
        if 매치번호 == 3:
            semi_1 = matches.get("1", {}).get("winner")
            semi_2 = matches.get("2", {}).get("winner")
            if not semi_1 or not semi_2:
                return await interaction.followup.send("⚠️ 결승은 매치 1, 매치 2 승리팀이 모두 기록된 뒤 입력할 수 있습니다.")
            match["team_nos"] = [semi_1, semi_2]
    
        winner_no = parse_league_team(승리팀)
        if winner_no is None:
            return await interaction.followup.send(f"🏆 승리팀은 `1`~`4` 또는 `{LEAGUE_MODE_NAME} 1팀`처럼 입력해주세요.")
        if winner_no not in match.get("team_nos", []):
            teams_text = ", ".join(f"{team_no}팀" for team_no in match.get("team_nos", []))
            return await interaction.followup.send(f"⚠️ 매치 {매치번호}의 참가팀은 {teams_text} 입니다.")
    
        teams = game_state.get("teams", [])
        winner_team = next((team for team in teams if team.get("team_no") == winner_no), None)
        loser_no = next(team_no for team_no in match.get("team_nos", []) if team_no != winner_no)
        loser_team = next((team for team in teams if team.get("team_no") == loser_no), None)
        if not winner_team or not loser_team:
            return await interaction.followup.send(f"❌ {LEAGUE_MODE_NAME} 팀 정보를 찾을 수 없습니다.")
    
        bot.user_data.setdefault(gid, {})
        player_records = []
        for team, result in ((winner_team, "win"), (loser_team, "loss")):
            for uid_str in team.get("players", []):
                display_name = (team.get("player_names", {}) or {}).get(str(uid_str))
                if not display_name:
                    member = interaction.guild.get_member(int(uid_str))
                    if not member:
                        try:
                            member = await interaction.guild.fetch_member(int(uid_str))
                        except (discord.NotFound, discord.HTTPException, ValueError):
                            member = None
                    display_name = member.display_name if member else f"UID {uid_str}"
                if not is_simulation:
                    if uid_str not in bot.user_data[gid]:
                        bot.user_data[gid][uid_str] = make_default_user(display_name)
                    ud = ensure_user_format(bot.user_data[gid][uid_str])
                    league_stats = ud["league_stats"]
                    if result == "win":
                        league_stats["match_win"] += 1
                    else:
                        league_stats["match_loss"] += 1
                player_records.append({
                    "user_id": uid_str,
                    "name": display_name,
                    "team": team.get("name"),
                    "result": result,
                })
    
        match["winner"] = winner_no
        round_no = int(game_state.get("round_no") or get_next_league_round(gid))
        description = f"`매치 {매치번호}` **{format_league_team_name(winner_team)}** 승리 기록 완료"
        final_blue_team = None
        final_red_team = None
    
        def build_stored_team_lines(team):
            roles_map = team.get("roles", {}) or {}
            player_names = team.get("player_names", {}) or {}
            player_scores = team.get("player_scores", {}) or {}
            lines = []
            for role in ROLES:
                uid = roles_map.get(role)
                if not uid:
                    lines.append(f"{get_role_display_marker(role, interaction.guild)} 기록 없음")
                    continue
    
                uid_key = str(uid)
                name = player_names.get(uid_key) or get_member_display_name(interaction.guild, gid, uid_key)
                score = int(player_scores.get(uid_key, 0) or 0)
                if score > 0:
                    tier_name = get_tier_name(score)
                    emoji = get_tier_emoji(tier_name, interaction.guild, gid)
                    score_text = f" `{score}`"
                else:
                    emoji = get_user_peak_tier_emoji(gid, uid_key, interaction.guild)
                    score_text = ""
                lines.append(f"{get_role_display_marker(role, interaction.guild)}{score_text} {emoji} {discord.utils.escape_markdown(name)}")
            return "\n".join(lines)
    
        def build_stored_power_gap_line(blue_team, red_team):
            blue_total = int(blue_team.get("total", 0) or 0)
            red_total = int(red_team.get("total", 0) or 0)
            gap = blue_total - red_total
            if gap == 0:
                return "전력차 **0** · 균형"
            favored_no = blue_team["team_no"] if gap > 0 else red_team["team_no"]
            return f"전력차 **{abs(gap)}** · {favored_no}팀 우세"
    
        def build_stored_match_field_value(blue_team, red_team):
            blue_total = int(blue_team.get("total", 0) or 0)
            red_total = int(red_team.get("total", 0) or 0)
            return (
                f"🔵 **{blue_team['team_no']}팀** `{blue_total}`  vs  `{red_total}` **{red_team['team_no']}팀** 🔴\n"
                f"{build_stored_power_gap_line(blue_team, red_team)}\n\n"
                f"**BLUE {blue_team['team_no']}팀**\n"
                f"{build_stored_team_lines(blue_team)}\n\n"
                f"**RED {red_team['team_no']}팀**\n"
                f"{build_stored_team_lines(red_team)}\n\n"
                f"`/승리 {get_queue_label(queue_key)} 3 [승리팀번호]` 로 결승 결과를 입력하세요."
            )
    
        if 매치번호 in (1, 2):
            semi_1 = matches.get("1", {}).get("winner")
            semi_2 = matches.get("2", {}).get("winner")
            if semi_1 and semi_2:
                matches["3"]["team_nos"] = [semi_1, semi_2]
                final_blue_team = next((team for team in teams if team.get("team_no") == semi_1), None)
                final_red_team = next((team for team in teams if team.get("team_no") == semi_2), None)
        else:
            if is_simulation:
                game_state["pending_champion_name"] = {
                    "round_no": round_no,
                    "winner_no": winner_no,
                    "loser_no": loser_no,
                    "created_at": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
                }
                embed = discord.Embed(
                    title=f"🏆 협곡 리그전 {round_no}회차 결승 결과 (시뮬레이션)",
                    description=(
                        f"✨ **{format_league_team_name(winner_team)}**이 협곡 리그전 {round_no}회차 우승팀이 되었습니다. 축하드립니다!\n"
                        "실제 협곡 리그전이라면 우승팀 이름 입력 후 명예의전당 기록 단계로 이어집니다."
                    ),
                    color=0xf1c40f
                )
                embed.add_field(name=f"🥇 우승팀 · {format_league_team_name(winner_team)}", value=format_league_role_lines(interaction.guild, gid, winner_team), inline=False)
                embed.add_field(name=f"🥈 준우승팀 · {format_league_team_name(loser_team)}", value=format_league_role_lines(interaction.guild, gid, loser_team), inline=False)
                embed.set_footer(text="시뮬레이션 결과는 저장되지 않으며 MMR, 전적, 우승 기록, 음성 채널에는 영향을 주지 않습니다.")
                await send_league_sim_output(
                    interaction,
                    gid,
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                guide_embed = discord.Embed(
                    title="📝 우승팀 이름 입력 대기 (시뮬레이션)",
                    description=(
                        "`/우승팀입력 [팀이름]` 으로 최종 등록 화면까지 시뮬레이션할 수 있습니다.\n"
                        "시뮬레이션이므로 실제 명예의전당, 칭호, 전적에는 반영되지 않습니다."
                    ),
                    color=0x3498db
                )
                return await send_league_sim_output(
                    interaction,
                    gid,
                    embed=guide_embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                    notify=False,
                )
    
            game_state["pending_champion_name"] = {
                "round_no": round_no,
                "winner_no": winner_no,
                "loser_no": loser_no,
                "created_at": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            }
            bot.save_lucid_data(gid)
            await move_members_to_waiting_voice(
                interaction.guild,
                list(winner_team.get("players", [])) + list(loser_team.get("players", []))
            )
            embed = discord.Embed(
                title=f"🏆 협곡 리그전 {round_no}회차 결승 결과",
                description=(
                    f"✨ **{format_league_team_name(winner_team)}**이 협곡 리그전 {round_no}회차 우승팀이 되었습니다. 축하드립니다!\n"
                    "우승팀 이름 입력 후 명예의전당 기록 단계로 이어집니다."
                ),
                color=0xf1c40f
            )
            embed.add_field(name=f"🥇 우승팀 · {format_league_team_name(winner_team)}", value=format_league_role_lines(interaction.guild, gid, winner_team), inline=False)
            embed.add_field(name=f"🥈 준우승팀 · {format_league_team_name(loser_team)}", value=format_league_role_lines(interaction.guild, gid, loser_team), inline=False)
            embed.set_footer(text="결승 매치 결과 기록 완료")
            await send_league_output(interaction, gid, embed=embed, notify=True)
            guide_embed = discord.Embed(
                title="📝 우승팀 이름 입력 대기",
                description=(
                    "우승팀 중 한 명은 `/우승팀입력 [팀이름]` 명령어로 팀 이름을 입력해주세요.\n"
                    "입력한 팀 이름으로 우승 기록과 명예의전당이 최종 확정됩니다.\n\n"
                    "1시간 동안 입력이 없으면 팀 이름 없이 자동으로 명예의전당에 기록됩니다."
                ),
                color=0x3498db
            )
            await send_league_output(
                interaction,
                gid,
                embed=guide_embed,
                allowed_mentions=discord.AllowedMentions.none(),
                notify=False,
            )
            return
    
        if not is_simulation:
            await move_members_to_waiting_voice(
                interaction.guild,
                list(winner_team.get("players", [])) + list(loser_team.get("players", []))
            )
            match_id = f"{now_kst().strftime('%Y%m%d%H%M%S')}-league-m{매치번호}"
            append_match_history(gid, {
                "id": match_id,
                "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
                "queue": LEAGUE_QUEUE_KEY,
                "mode": LEAGUE_MODE_KEY,
                "round": round_no,
                "match_no": 매치번호,
                "winner": winner_team.get("name"),
                "teams": [
                    {"name": winner_team.get("name"), "team_no": winner_no, "players": winner_team.get("players", [])},
                    {"name": loser_team.get("name"), "team_no": loser_no, "players": loser_team.get("players", [])},
                ],
                "players": player_records,
                "cancelled": False
            })
    
        if game_state.get("finalized"):
            ensure_guild_queues(gid)[LEAGUE_QUEUE_KEY] = []
            bot.active_games.get(gid, {}).pop(LEAGUE_QUEUE_KEY, None)
            try:
                await cleanup_vcs(interaction.guild, LEAGUE_QUEUE_KEY, game_state)
            except Exception as e:
                logger.warning(f"{LEAGUE_MODE_NAME} 음성 채널 정리 중 오류: {e}")
    
        if not is_simulation:
            bot.save_lucid_data(gid)
    
        final_match_embed = None
        embed = discord.Embed(
            title=(
                f"🧪 {LEAGUE_SIM_LABEL} 매치 {매치번호} 결과 기록 완료"
                if is_simulation else
                f"🏆 {LEAGUE_MODE_NAME} {round_no}회차 매치 {매치번호} 결과 기록 완료"
            ),
            description=description,
            color=0x9b59b6
        )
        embed.add_field(name=f"승리팀 · {format_league_team_name(winner_team)}", value=format_league_role_lines(interaction.guild, gid, winner_team), inline=False)
        embed.add_field(name=f"패배팀 · {format_league_team_name(loser_team)}", value=format_league_role_lines(interaction.guild, gid, loser_team), inline=False)
        if final_blue_team and final_red_team:
            final_match_embed = build_league_match_detail_embed(
                interaction.guild,
                gid,
                3,
                final_blue_team,
                final_red_team,
                footer_text=(
                    "시뮬레이션 결과는 저장되지 않고 MMR과 전적에 영향을 주지 않습니다."
                    if is_simulation else
                    "결승 대진이 생성되었습니다."
                ),
            )
            final_match_embed.add_field(
                name="다음 입력",
                value=f"`/승리 {get_queue_label(queue_key)} 3 [승리팀번호]` 로 결승 결과를 입력하세요.",
                inline=False
            )
        if is_simulation and not (final_blue_team and final_red_team):
            if matches.get("1", {}).get("winner") and matches.get("2", {}).get("winner"):
                embed.add_field(
                    name="다음 입력",
                    value=f"`/승리 {LEAGUE_SIM_LABEL} 3 [승리팀번호]` 로 결승 결과를 입력하세요.",
                    inline=False
                )
            embed.set_footer(text="시뮬레이션 결과는 저장되지 않고 MMR과 전적에 영향을 주지 않습니다.")
        send_output = send_league_sim_output if is_simulation else send_league_output
        await send_output(
            interaction,
            gid,
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        if final_match_embed:
            if not is_simulation:
                await move_stored_league_teams_to_existing_voice_channels(
                    interaction.guild,
                    [final_blue_team, final_red_team],
                    mode_name=LEAGUE_MODE_NAME,
                )
            await send_output(
                interaction,
                gid,
                embed=final_match_embed,
                allowed_mentions=discord.AllowedMentions.none(),
                notify=False,
            )
        return
    
    def normalize_team_name_key(value):
        return re.sub(r"[\s\u200b\u200c\u200d]+", "", str(value or "").strip().lower())
    
    def parse_series_team_identifier(value, teams, allowed_team_nos=None):
        team_no = parse_league_team(value)
        allowed = {int(no) for no in allowed_team_nos or [] if no}
        if team_no and (not allowed or team_no in allowed):
            return team_no
        key = normalize_team_name_key(value)
        if not key:
            return None
        for team in teams:
            no = int(team.get("team_no", 0) or 0)
            if allowed and no not in allowed:
                continue
            names = {
                normalize_team_name_key(team.get("name")),
                normalize_team_name_key(format_league_team_name(team)),
                normalize_team_name_key(f"{no}팀"),
            }
            if key in names:
                return no
        return None
    
    def build_series_match_history_record(gid, game_state, match, winner_team, loser_team):
        player_records = []
        is_aram_league = game_state.get("mode") == ARAM_LEAGUE_MODE_KEY
        for team, result in ((winner_team, "win"), (loser_team, "loss")):
            roles = team.get("roles", {}) or {}
            scores = team.get("player_scores", {}) or {}
            names = team.get("player_names", {}) or {}
            if is_aram_league:
                member_pairs = [(None, str(uid)) for uid in team.get("players", []) or []]
            else:
                member_pairs = [(role, str(roles.get(role) or "")) for role in ROLES]
            for role, uid in member_pairs:
                if not uid:
                    continue
                player_records.append({
                    "user_id": uid,
                    "name": names.get(uid, get_member_display_name(None, gid, uid)),
                    "team": format_league_team_name(team),
                    "role": role,
                    "result": result,
                    "before_mmr": int(scores.get(uid, 0) or 0),
                })
        queue_key = get_series_queue_key(game_state)
        mode_key = game_state.get("mode") or LEAGUE_SERIES_MODE_KEY
        match_id = f"{now_kst().strftime('%Y%m%d%H%M%S')}-{queue_key}-m{match.get('match_no')}"
        return {
            "id": match_id,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            "queue": queue_key,
            "mode": mode_key,
            "round": game_state.get("round_no"),
            "match_no": match.get("match_no"),
            "round_name": match.get("round_name"),
            "winner": format_league_team_name(winner_team),
            "teams": [
                {"name": format_league_team_name(winner_team), "team_no": winner_team.get("team_no"), "players": winner_team.get("players", [])},
                {"name": format_league_team_name(loser_team), "team_no": loser_team.get("team_no"), "players": loser_team.get("players", [])},
            ],
            "players": player_records,
            "cancelled": False,
        }
    
    async def process_league_series_win(interaction, gid, match_no, winner_text, game_state):
        is_simulation = bool(game_state.get("simulation"))
        is_aram_league = game_state.get("mode") == ARAM_LEAGUE_MODE_KEY
        series_name = get_series_mode_name(game_state)
        queue_key = get_series_queue_key(game_state)
        matches = game_state.get("matches", {})
        match = matches.get(str(match_no))
        if not match:
            return await interaction.followup.send(f"❌ {series_name} 매치 {match_no} 정보를 찾을 수 없습니다.")
        if match.get("winner"):
            return await interaction.followup.send(f"⚠️ 매치 {match_no}는 이미 승리팀이 기록되어 있습니다.")
        team_nos = get_series_match_team_nos(match, matches)
        if not team_nos or any(no is None for no in team_nos):
            return await interaction.followup.send(f"⚠️ 매치 {match_no}는 아직 이전 라운드 승자가 정해지지 않았습니다.")
    
        teams = game_state.get("teams", [])
        teams_by_no = {int(team.get("team_no")): team for team in teams}
        winner_no = parse_series_team_identifier(winner_text, teams, team_nos)
        if winner_no is None:
            teams_text = ", ".join(format_league_team_name(teams_by_no.get(int(no), {"team_no": no})) for no in team_nos)
            return await interaction.followup.send(f"🏆 매치 {match_no} 승리팀은 {teams_text} 중 하나로 입력해주세요.")
        loser_no = next(no for no in team_nos if int(no) != int(winner_no))
        winner_team = teams_by_no.get(int(winner_no))
        loser_team = teams_by_no.get(int(loser_no))
        if not winner_team or not loser_team:
            return await interaction.followup.send("❌ 팀 정보를 찾지 못했습니다.")
    
        bot.user_data.setdefault(gid, {})
        history_record = build_series_match_history_record(gid, game_state, match, winner_team, loser_team)
        playable_before = {
            str(mid)
            for mid in game_state.get("match_order", [])
            if is_series_match_playable(matches.get(str(mid), {}), matches)
        }
        if not is_simulation:
            stat_key = "aram_league_stats" if is_aram_league else "league_stats"
            for player in history_record.get("players", []):
                uid = str(player.get("user_id"))
                if uid not in bot.user_data[gid]:
                    bot.user_data[gid][uid] = make_default_user(player.get("name", uid))
                ud = ensure_user_format(bot.user_data[gid][uid])
                if player.get("result") == "win":
                    ud[stat_key]["match_win"] += 1
                else:
                    ud[stat_key]["match_loss"] += 1

        match["winner"] = int(winner_no)
        playable_after = {
            str(mid)
            for mid in game_state.get("match_order", [])
            if is_series_match_playable(matches.get(str(mid), {}), matches)
        }
        newly_ready_match_ids = playable_after - playable_before
        if not is_simulation:
            append_match_history(gid, history_record)
            await move_members_to_waiting_voice(
                interaction.guild,
                list(winner_team.get("players", [])) + list(loser_team.get("players", [])),
            )

        final_match_id = next(
            (str(mid) for mid in game_state.get("match_order", []) if matches.get(str(mid), {}).get("round_name") == "결승"),
            None,
        )
        third_place_match_id = next(
            (str(mid) for mid in game_state.get("match_order", []) if matches.get(str(mid), {}).get("placement") == "third_place"),
            None,
        )
        final_match = matches.get(str(final_match_id), {}) if final_match_id else {}
        third_place_match = matches.get(str(third_place_match_id), {}) if third_place_match_id else {}
        is_final = str(match_no) == str(final_match_id)
        is_third_place = str(match_no) == str(third_place_match_id)
        final_done = bool(final_match.get("winner"))
        third_place_done = not third_place_match_id or bool(third_place_match.get("winner"))
        should_finalize = final_done and third_place_done
    
        final_team_nos = get_series_match_team_nos(final_match, matches) if final_match else []
        champion_team = None
        runner_up_team = None
        third_team = None
        fourth_team = None
        if final_done and len(final_team_nos) == 2:
            champion_no = int(final_match.get("winner"))
            runner_up_no = next(int(no) for no in final_team_nos if int(no) != champion_no)
            champion_team = teams_by_no.get(champion_no)
            runner_up_team = teams_by_no.get(runner_up_no)
        if third_place_match_id and third_place_done:
            third_team_nos = get_series_match_team_nos(third_place_match, matches)
            if len(third_team_nos) == 2:
                third_no = int(third_place_match.get("winner"))
                fourth_no = next(int(no) for no in third_team_nos if int(no) != third_no)
                third_team = teams_by_no.get(third_no)
                fourth_team = teams_by_no.get(fourth_no)
    
        if should_finalize and champion_team and runner_up_team:
            finalist_nos = {int(champion_team.get("team_no")), int(runner_up_team.get("team_no"))}
            if not is_simulation:
                stat_key = "aram_league_stats" if is_aram_league else "league_stats"
                for team in teams:
                    for uid in team.get("players", []):
                        if str(uid) not in bot.user_data[gid]:
                            bot.user_data[gid][str(uid)] = make_default_user(get_member_display_name(interaction.guild, gid, uid))
                        ud = ensure_user_format(bot.user_data[gid][str(uid)])
                        ud[stat_key]["participations"] += 1
                        if not is_aram_league and int(team.get("team_no")) not in finalist_nos:
                            ud["league_stats"]["win_streak"] = 0
                            ud["league_stats"]["runner_up_streak"] = 0
                for uid in champion_team.get("players", []):
                    ud = ensure_user_format(bot.user_data[gid][str(uid)])
                    ud[stat_key]["wins"] += 1
                    if not is_aram_league:
                        ud["league_stats"]["win_streak"] = ud["league_stats"].get("win_streak", 0) + 1
                        ud["league_stats"]["runner_up_streak"] = 0
                for uid in runner_up_team.get("players", []):
                    ud = ensure_user_format(bot.user_data[gid][str(uid)])
                    ud[stat_key]["runner_ups"] += 1
                    if not is_aram_league:
                        ud["league_stats"]["win_streak"] = 0
                        ud["league_stats"]["runner_up_streak"] = ud["league_stats"].get("runner_up_streak", 0) + 1
                if third_team:
                    for uid in third_team.get("players", []):
                        ud = ensure_user_format(bot.user_data[gid][str(uid)])
                        ud[stat_key]["third_places"] += 1
    
                if is_aram_league:
                    round_no = int(game_state.get("round_no") or get_next_aram_league_round(gid))
                    set_aram_league_round(gid, round_no)
                else:
                    round_no = int(game_state.get("round_no") or get_next_league_series_round(gid))
                    if round_no == 1:
                        await grant_first_team_title(
                            interaction,
                            gid,
                            list(champion_team.get("players", [])),
                            "inaugural_champion",
                        )
                    for team in teams:
                        for uid in team.get("players", []):
                            await check_league_title_unlocks(interaction, gid, uid)
                    set_league_series_round(gid, round_no)
                    champion_record = {
                        "round": round_no,
                        "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
                        "mode": LEAGUE_SERIES_MODE_KEY,
                        "winner": {
                            "team_no": champion_team.get("team_no"),
                            "name": champion_team.get("name"),
                            "players": list(champion_team.get("players", [])),
                            "roles": dict(champion_team.get("roles", {})),
                        },
                        "runner_up": {
                            "team_no": runner_up_team.get("team_no"),
                            "name": runner_up_team.get("name"),
                            "players": list(runner_up_team.get("players", [])),
                            "roles": dict(runner_up_team.get("roles", {})),
                        },
                    }
                    if third_team and fourth_team:
                        champion_record["third_place"] = {
                            "team_no": third_team.get("team_no"),
                            "name": third_team.get("name"),
                            "players": list(third_team.get("players", [])),
                            "roles": dict(third_team.get("roles", {})),
                        }
                        champion_record["fourth_place"] = {
                            "team_no": fourth_team.get("team_no"),
                            "name": fourth_team.get("name"),
                            "players": list(fourth_team.get("players", [])),
                            "roles": dict(fourth_team.get("roles", {})),
                        }
                    get_league_champions(gid).append(champion_record)
            game_state["finalized"] = True
            queue_to_clear = LEAGUE_SERIES_SIM_QUEUE_KEY if is_simulation else queue_key
            bot.active_games.get(gid, {}).pop(queue_to_clear, None)
            if not is_simulation:
                try:
                    await cleanup_vcs(interaction.guild, queue_key, game_state)
                except Exception as e:
                    logger.warning(f"{series_name} 음성 채널 정리 중 오류: {e}")
    
        if not is_simulation:
            bot.save_lucid_data(gid)
        embed = build_league_series_embed(interaction.guild, gid, game_state, title_suffix="결과 갱신")
        embed.description = (
            f"`매치 {match_no}` **{format_league_team_name(winner_team)}** 승리 기록 완료\n"
            + (
                "최종 순위가 확정되었습니다."
                if should_finalize else
                ("결승 결과가 입력되었습니다. 3/4위전 결과를 입력하면 최종 순위가 확정됩니다." if is_final and third_place_match_id else "다음 매치가 준비되면 같은 방식으로 결과를 입력해주세요.")
            )
        )
        if should_finalize and champion_team and runner_up_team:
            embed.add_field(name=format_league_result_field_name("🥇", "1등", champion_team), value=format_league_series_role_lines(interaction.guild, gid, champion_team), inline=False)
            embed.add_field(name=format_league_result_field_name("🥈", "2등", runner_up_team), value=format_league_series_role_lines(interaction.guild, gid, runner_up_team), inline=False)
            if third_team:
                embed.add_field(name=format_league_result_field_name("🥉", "3등", third_team), value=format_league_series_role_lines(interaction.guild, gid, third_team), inline=False)
        send_output = send_league_sim_output if is_simulation else send_league_output
        await send_output(interaction, gid, embed=embed, allowed_mentions=discord.AllowedMentions.none())
        if newly_ready_match_ids:
            for ready_match_id in game_state.get("match_order", []):
                if str(ready_match_id) not in newly_ready_match_ids:
                    continue
                ready_match = matches.get(str(ready_match_id), {})
                detail_embed = build_league_series_match_detail_embed(
                    interaction.guild,
                    gid,
                    ready_match,
                    matches,
                    teams_by_no,
                    game_state,
                )
                if detail_embed:
                    await send_output(
                        interaction,
                        gid,
                        embed=detail_embed,
                        allowed_mentions=discord.AllowedMentions.none(),
                        notify=False,
                    )
        return history_record
    
    def parse_league_pending_created_at(pending):
        text = str((pending or {}).get("created_at") or "").strip()
        if not text:
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    
    async def finalize_expired_league_champion_name(guild, gid):
        game_state = bot.active_games.get(gid, {}).get(LEAGUE_QUEUE_KEY)
        if not game_state or game_state.get("mode") != LEAGUE_MODE_KEY:
            return False
        if game_state.get("simulation") or game_state.get("finalized"):
            return False
    
        pending = game_state.get("pending_champion_name")
        if not pending:
            return False
        created_at = parse_league_pending_created_at(pending)
        if not created_at:
            created_at = now_kst()
            pending["created_at"] = created_at.strftime("%Y-%m-%d %H:%M:%S")
            bot.save_lucid_data(gid)
            return False
        if (now_kst() - created_at).total_seconds() < LEAGUE_CHAMPION_NAME_TIMEOUT_SECONDS:
            return False
    
        process_key = (gid, LEAGUE_QUEUE_KEY)
        if process_key in bot.processing_games or game_state.get("_auto_finalizing_champion") or game_state.get("_champion_name_finalizing"):
            return False
    
        teams = game_state.get("teams", [])
        matches = game_state.setdefault("matches", {})
        try:
            round_no = int(pending.get("round_no") or game_state.get("round_no") or get_next_league_round(gid))
            winner_no = int(pending.get("winner_no"))
            loser_no = int(pending.get("loser_no"))
        except (TypeError, ValueError):
            logger.warning("토너먼트 우승팀 이름 자동 확정 실패: 잘못된 pending 데이터 guild=%s pending=%s", gid, pending)
            return False
    
        winner_team = next((team for team in teams if team.get("team_no") == winner_no), None)
        loser_team = next((team for team in teams if team.get("team_no") == loser_no), None)
        if not winner_team or not loser_team:
            logger.warning("토너먼트 우승팀 이름 자동 확정 실패: 팀 정보 없음 guild=%s", gid)
            return False
    
        channel = await get_league_output_channel(guild, gid)
        if not channel:
            channel = await get_queue_notice_channel(guild, gid)
        fake_interaction = SimpleNamespace(guild=guild, channel=channel)
        fallback_winner_name = f"{round_no}회차 우승팀"
    
        bot.processing_games.add(process_key)
        game_state["_auto_finalizing_champion"] = True
        previous_title_batch = bot.title_batch
        if bot.title_batch is None:
            bot.title_batch = {}
        bot.title_batch[gid] = []
    
        try:
            bot.user_data.setdefault(gid, {})
            winner_team["name"] = None
            match = matches.setdefault("3", {"team_nos": [winner_no, loser_no], "winner": winner_no})
            match["team_nos"] = [winner_no, loser_no]
            match["winner"] = winner_no
    
            for team in teams:
                for uid_str in team.get("players", []):
                    if uid_str not in bot.user_data[gid]:
                        bot.user_data[gid][uid_str] = make_default_user(get_member_display_name(guild, gid, uid_str))
                    ud = ensure_user_format(bot.user_data[gid][uid_str])
                    ud["league_stats"]["participations"] += 1
    
            for uid_str in winner_team.get("players", []):
                ud = ensure_user_format(bot.user_data[gid][uid_str])
                ud["league_stats"]["wins"] += 1
                ud["league_stats"]["win_streak"] = ud["league_stats"].get("win_streak", 0) + 1
                ud["league_stats"]["runner_up_streak"] = 0
    
            for uid_str in loser_team.get("players", []):
                ud = ensure_user_format(bot.user_data[gid][uid_str])
                ud["league_stats"]["runner_ups"] += 1
                ud["league_stats"]["win_streak"] = 0
                ud["league_stats"]["runner_up_streak"] = ud["league_stats"].get("runner_up_streak", 0) + 1
    
            for team in teams:
                if team.get("team_no") in (winner_no, loser_no):
                    continue
                for uid_str in team.get("players", []):
                    ud = ensure_user_format(bot.user_data[gid][uid_str])
                    ud["league_stats"]["win_streak"] = 0
                    ud["league_stats"]["runner_up_streak"] = 0
    
            if round_no == 1:
                await grant_first_team_title(fake_interaction, gid, list(winner_team.get("players", [])), "inaugural_champion")
    
            for team in teams:
                for uid_str in team.get("players", []):
                    await check_league_title_unlocks(fake_interaction, gid, uid_str)
    
            set_league_round(gid, round_no)
            get_league_champions(gid).append({
                "round": round_no,
                "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
                "winner": {
                    "team_no": winner_no,
                    "name": None,
                    "players": list(winner_team.get("players", [])),
                    "roles": dict(winner_team.get("roles", {})),
                },
                "runner_up": {
                    "team_no": loser_no,
                    "name": loser_team.get("name"),
                    "players": list(loser_team.get("players", [])),
                    "roles": dict(loser_team.get("roles", {})),
                },
            })
    
            player_records = []
            for team, result in ((winner_team, "win"), (loser_team, "loss")):
                for uid_str in team.get("players", []):
                    player_records.append({
                        "user_id": uid_str,
                        "name": get_member_display_name(guild, gid, uid_str),
                        "team": team.get("name"),
                        "result": result,
                    })
    
            match_id = f"{now_kst().strftime('%Y%m%d%H%M%S')}-league-m3-auto"
            append_match_history(gid, {
                "id": match_id,
                "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
                "queue": LEAGUE_QUEUE_KEY,
                "mode": LEAGUE_MODE_KEY,
                "round": round_no,
                "match_no": 3,
                "winner": fallback_winner_name,
                "teams": [
                    {"name": None, "team_no": winner_no, "players": winner_team.get("players", [])},
                    {"name": loser_team.get("name"), "team_no": loser_no, "players": loser_team.get("players", [])},
                ],
                "players": player_records,
                "cancelled": False
            })
    
            game_state["finalized"] = True
            game_state.pop("pending_champion_name", None)
            ensure_guild_queues(gid)[LEAGUE_QUEUE_KEY] = []
            bot.active_games.get(gid, {}).pop(LEAGUE_QUEUE_KEY, None)
            try:
                await cleanup_vcs(guild, LEAGUE_QUEUE_KEY, game_state)
            except Exception as e:
                logger.warning(f"{LEAGUE_MODE_NAME} 음성 채널 정리 중 오류: {e}")
            bot.save_lucid_data(gid)
    
            if channel:
                embed = discord.Embed(
                    title=f"🏛️ 협곡 리그전 {round_no}회차 우승팀 자동 기록",
                    description=(
                        "우승팀 이름 입력 대기 시간이 1시간을 넘어 자동 확정되었습니다.\n"
                        "**팀 이름 없이** 명예의전당에 기록됩니다."
                    ),
                    color=0x95a5a6
                )
                embed.add_field(
                    name=format_league_result_field_name("🥇", "우승팀", winner_team),
                    value=format_league_role_lines(guild, gid, winner_team),
                    inline=False
                )
                embed.add_field(
                    name=format_league_result_field_name("🥈", "준우승팀", loser_team),
                    value=format_league_role_lines(guild, gid, loser_team),
                    inline=False
                )
                embed.set_footer(text="개인 우승/준우승 기록과 칭호 조건은 정상 반영되었습니다.")
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    
            await flush_title_batch(fake_interaction, gid)
            return True
        except Exception:
            logger.exception("토너먼트 우승팀 이름 자동 확정 중 오류: guild=%s", gid)
            return False
        finally:
            game_state.pop("_auto_finalizing_champion", None)
            bot.processing_games.discard(process_key)
            if previous_title_batch is None and bot.title_batch == {}:
                bot.title_batch = None
    
    @bot.tree.command(name="우승팀입력", description="협곡 리그전 우승팀 멤버가 우승팀 이름을 입력하고 우승 기록을 확정합니다.")
    async def set_league_champion_team_name(interaction: discord.Interaction, 팀이름: str):
        gid = str(interaction.guild_id)
        active_games = bot.active_games.get(gid, {})
        game_state = active_games.get(LEAGUE_QUEUE_KEY)
        queue_key = LEAGUE_QUEUE_KEY
        if not game_state:
            game_state = active_games.get(LEAGUE_SIM_QUEUE_KEY)
            queue_key = LEAGUE_SIM_QUEUE_KEY
        if not game_state or game_state.get("mode") != LEAGUE_MODE_KEY:
            return await interaction.response.send_message(f"⚠️ 현재 팀 이름 입력을 기다리는 {LEAGUE_MODE_NAME}이 없습니다.", ephemeral=True)
        is_simulation = bool(game_state.get("simulation")) or queue_key == LEAGUE_SIM_QUEUE_KEY
    
        pending = game_state.get("pending_champion_name")
        if not pending:
            return await interaction.response.send_message("⚠️ 현재 우승팀 이름 입력 단계가 아닙니다.", ephemeral=True)
        if game_state.get("_champion_name_finalizing") or game_state.get("_auto_finalizing_champion"):
            return await interaction.response.send_message("⏳ 우승팀 기록 확정이 이미 처리 중입니다. 잠시만 기다려주세요.", ephemeral=True)
    
        team_name = " ".join(str(팀이름).strip().split())
        if not team_name:
            return await interaction.response.send_message("⚠️ 우승팀 이름을 입력해주세요.", ephemeral=True)
        if len(team_name) > 30:
            return await interaction.response.send_message("⚠️ 우승팀 이름은 30자 이하로 입력해주세요.", ephemeral=True)
    
        teams = game_state.get("teams", [])
        matches = game_state.setdefault("matches", {})
        round_no = int(pending.get("round_no") or game_state.get("round_no") or get_next_league_round(gid))
        winner_no = int(pending.get("winner_no"))
        loser_no = int(pending.get("loser_no"))
        winner_team = next((team for team in teams if team.get("team_no") == winner_no), None)
        loser_team = next((team for team in teams if team.get("team_no") == loser_no), None)
        if not winner_team or not loser_team:
            return await interaction.response.send_message(f"❌ {LEAGUE_MODE_NAME} 팀 정보를 찾을 수 없습니다.", ephemeral=True)
    
        if is_simulation and not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 시뮬레이션 우승팀 이름 입력은 운영 권한이 필요합니다.", ephemeral=True)
        if not is_simulation and str(interaction.user.id) not in set(map(str, winner_team.get("players", []))):
            return await interaction.response.send_message("🚫 우승팀 이름은 우승팀 멤버만 입력할 수 있습니다.", ephemeral=True)
    
        game_state["_champion_name_finalizing"] = True
        await interaction.response.defer()
    
        bot.user_data.setdefault(gid, {})
        winner_team["name"] = team_name
        match = matches.setdefault("3", {"team_nos": [winner_no, loser_no], "winner": winner_no})
        match["team_nos"] = [winner_no, loser_no]
        match["winner"] = winner_no
    
        if is_simulation:
            game_state["finalized"] = True
            game_state.pop("pending_champion_name", None)
            bot.active_games.get(gid, {}).pop(LEAGUE_SIM_QUEUE_KEY, None)
            embed = discord.Embed(
                title=f"🏛️ 협곡 리그전 {round_no}회차 우승팀 (시뮬레이션)",
                description=(
                    f"**{discord.utils.escape_markdown(team_name)}**\n"
                    "실제 협곡 리그전이라면 명예의전당에 기록됩니다. 축하드립니다!"
                ),
                color=0xf1c40f
            )
            embed.add_field(
                name=format_league_result_field_name("🥇", "우승팀", winner_team),
                value=format_league_role_lines(interaction.guild, gid, winner_team),
                inline=False
            )
            embed.add_field(
                name=format_league_result_field_name("🥈", "준우승팀", loser_team),
                value=format_league_role_lines(interaction.guild, gid, loser_team),
                inline=False
            )
            embed.set_footer(text="시뮬레이션 결과는 저장되지 않으며 칭호와 명예의전당에도 반영되지 않습니다.")
            game_state.pop("_champion_name_finalizing", None)
            return await send_league_sim_output(
                interaction,
                gid,
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
    
        for team in teams:
            for uid_str in team.get("players", []):
                if uid_str not in bot.user_data[gid]:
                    bot.user_data[gid][uid_str] = make_default_user(get_member_display_name(interaction.guild, gid, uid_str))
                ud = ensure_user_format(bot.user_data[gid][uid_str])
                ud["league_stats"]["participations"] += 1
    
        for uid_str in winner_team.get("players", []):
            ud = ensure_user_format(bot.user_data[gid][uid_str])
            ud["league_stats"]["wins"] += 1
            ud["league_stats"]["win_streak"] = ud["league_stats"].get("win_streak", 0) + 1
            ud["league_stats"]["runner_up_streak"] = 0
    
        for uid_str in loser_team.get("players", []):
            ud = ensure_user_format(bot.user_data[gid][uid_str])
            ud["league_stats"]["runner_ups"] += 1
            ud["league_stats"]["win_streak"] = 0
            ud["league_stats"]["runner_up_streak"] = ud["league_stats"].get("runner_up_streak", 0) + 1
    
        for team in teams:
            if team.get("team_no") in (winner_no, loser_no):
                continue
            for uid_str in team.get("players", []):
                ud = ensure_user_format(bot.user_data[gid][uid_str])
                ud["league_stats"]["win_streak"] = 0
                ud["league_stats"]["runner_up_streak"] = 0
    
        if round_no == 1:
            await grant_first_team_title(interaction, gid, list(winner_team.get("players", [])), "inaugural_champion")
    
        for team in teams:
            for uid_str in team.get("players", []):
                await check_league_title_unlocks(interaction, gid, uid_str)
    
        set_league_round(gid, round_no)
        get_league_champions(gid).append({
            "round": round_no,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            "winner": {
                "team_no": winner_no,
                "name": team_name,
                "players": list(winner_team.get("players", [])),
                "roles": dict(winner_team.get("roles", {})),
            },
            "runner_up": {
                "team_no": loser_no,
                "name": loser_team.get("name"),
                "players": list(loser_team.get("players", [])),
                "roles": dict(loser_team.get("roles", {})),
            },
        })
    
        player_records = []
        for team, result in ((winner_team, "win"), (loser_team, "loss")):
            for uid_str in team.get("players", []):
                player_records.append({
                    "user_id": uid_str,
                    "name": get_member_display_name(interaction.guild, gid, uid_str),
                    "team": team.get("name"),
                    "result": result,
                })
    
        match_id = f"{now_kst().strftime('%Y%m%d%H%M%S')}-league-m3"
        append_match_history(gid, {
            "id": match_id,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            "queue": LEAGUE_QUEUE_KEY,
            "mode": LEAGUE_MODE_KEY,
            "round": round_no,
            "match_no": 3,
            "winner": team_name,
            "teams": [
                {"name": team_name, "team_no": winner_no, "players": winner_team.get("players", [])},
                {"name": loser_team.get("name"), "team_no": loser_no, "players": loser_team.get("players", [])},
            ],
            "players": player_records,
            "cancelled": False
        })
    
        game_state["finalized"] = True
        game_state.pop("pending_champion_name", None)
        ensure_guild_queues(gid)[LEAGUE_QUEUE_KEY] = []
        bot.active_games.get(gid, {}).pop(LEAGUE_QUEUE_KEY, None)
        try:
            await cleanup_vcs(interaction.guild, LEAGUE_QUEUE_KEY, game_state)
        except Exception as e:
            logger.warning(f"{LEAGUE_MODE_NAME} 음성 채널 정리 중 오류: {e}")
        bot.save_lucid_data(gid)
    
        embed = discord.Embed(
            title=f"🏛️ 협곡 리그전 {round_no}회차 우승팀",
            description=(
                f"**{discord.utils.escape_markdown(team_name)}**\n"
                "명예의전당에 기록됩니다. 축하드립니다!"
            ),
            color=0xf1c40f
        )
        embed.add_field(
            name=format_league_result_field_name("🥇", "우승팀", winner_team),
            value=format_league_role_lines(interaction.guild, gid, winner_team),
            inline=False
        )
        embed.add_field(
            name=format_league_result_field_name("🥈", "준우승팀", loser_team),
            value=format_league_role_lines(interaction.guild, gid, loser_team),
            inline=False
        )
        embed.set_footer(text="칭호 조건을 달성한 소환사는 별도의 퀘스트 달성 알림으로 표시됩니다.")
        game_state.pop("_champion_name_finalizing", None)
        await send_league_output(
            interaction,
            gid,
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    
    async def process_noban_win(interaction, gid, queue_key, winner_text, queue_keep, game_state):
        match_id = str(game_state.get("game_id") or f"{now_kst().strftime('%Y%m%d%H%M%S')}-noban-q{queue_key}")
        game_state.setdefault("game_id", match_id)
        if has_match_history_id(gid, match_id):
            bot.active_games.setdefault(gid, {}).pop(queue_key, None)
            bot.save_lucid_data(gid)
            logger.warning("중복 노밴 결과 요청 종료: guild_id=%s queue=%s match_id=%s", gid, queue_key, match_id)
            await interaction.followup.send("⚠️ 이미 기록이 끝난 경기입니다. 중복 결과는 반영하지 않았습니다.")
            return {"DUPLICATE": True, "match_id": match_id}
        is_blue_win = winner_text in ['블루', 'blue', '1', '🔵']
        if not mark_match_result_processing(gid, game_state, "blue" if is_blue_win else "red"):
            logger.error("중단된 노밴 결과 수동 복구 필요: guild_id=%s queue=%s match_id=%s", gid, queue_key, match_id)
            await interaction.followup.send("⚠️ 이전 결과 처리가 중간에 중단된 경기입니다. 중복 MMR 방지를 위해 자동 재처리를 막았습니다. `/리셋` 전 로그와 경기 기록을 확인해주세요.")
            return {"RECOVERY_REQUIRED": True, "match_id": match_id}
        winner_ids = game_state['blue'] if is_blue_win else game_state['red']
        loser_ids = game_state['red'] if is_blue_win else game_state['blue']
        roles_map = game_state.get('roles', {})
        rating_sources = game_state.get('rating_sources', {})
    
        match_players = []
        applied_deltas = {}
        pre_match_streaks = {}
        pre_role_streaks = {}
        pre_noban_stats = {}
        pre_rival_stats = snapshot_rival_stats(gid, winner_ids + loser_ids)
        for uid_str in (winner_ids + loser_ids):
            member = interaction.guild.get_member(int(uid_str))
            if not member:
                try:
                    member = await interaction.guild.fetch_member(int(uid_str))
                except (discord.NotFound, discord.HTTPException):
                    member = None
            display_name = member.display_name if member else f"UID {uid_str}"
            user_info = ensure_user_format(bot.user_data.setdefault(gid, {}).setdefault(uid_str, make_default_user(display_name)))
            played_role = roles_map.get(uid_str, "미지정")
            rating_source = rating_sources.get(uid_str) or get_noban_rating_source(user_info, played_role) or "normal"
            is_win = uid_str in winner_ids
    
            if rating_source == "noban":
                stats = user_info.setdefault("noban_stats", {"win": 0, "loss": 0})
                stats.setdefault("win", 0)
                stats.setdefault("loss", 0)
                pre_noban_stats[uid_str] = {
                    "mmr": get_noban_mmr(user_info),
                    "win": int(stats.get("win", 0) or 0),
                    "loss": int(stats.get("loss", 0) or 0),
                }
                before_mmr = get_noban_mmr(user_info)
                current_games = int(stats.get("win", 0) or 0) + int(stats.get("loss", 0) or 0)
                final_delta, delta_phase = get_role_match_delta_config(gid, current_games)
                if is_win:
                    stats["win"] = int(stats.get("win", 0) or 0) + 1
                    user_info["noban_mmr"] = before_mmr + final_delta
                    signed_delta = final_delta
                else:
                    stats["loss"] = int(stats.get("loss", 0) or 0) + 1
                    user_info["noban_mmr"] = max(0, before_mmr - final_delta)
                    signed_delta = -final_delta
                after_mmr = get_noban_mmr(user_info)
                applied_deltas[uid_str] = final_delta
            else:
                pre_match_streaks[uid_str] = user_info.get('streak', 0)
                user_info['role_stats'].setdefault(played_role, {'win': 0, 'loss': 0, 'streak': 0})
                pre_role_streaks[uid_str] = int(user_info['role_stats'][played_role].get('streak', 0) or 0)
                before_mmr = int(user_info['mmr'].get(played_role, 0) or 0)
                current_plays = int(user_info['plays'].get(played_role, 0) or 0)
                final_delta, delta_phase = get_role_match_delta_config(gid, current_plays)
                user_info['plays'][played_role] = current_plays + 1
                user_info['role_stats'].setdefault(played_role, {'win': 0, 'loss': 0})
                current_streak = int(user_info.get('streak', 0) or 0)
                current_role_streak = int(user_info['role_stats'][played_role].get('streak', 0) or 0)
                rating_result = shared_lol.calculate_classic_rating_result(
                    before_mmr,
                    final_delta,
                    current_role_streak,
                    is_win,
                    streak_adjustment_fn=shared_lol.get_streak_adjustment,
                )
                role_streak = rating_result["streak"]
                final_delta = rating_result["magnitude"]
                if is_win:
                    new_streak = current_streak + 1 if current_streak > 0 else 1
                    user_info['win'] += 1
                    user_info['role_stats'][played_role]['win'] += 1
                    user_info['mmr'][played_role] = before_mmr + final_delta
                    user_info['streak'] = new_streak
                    signed_delta = final_delta
                else:
                    new_streak = current_streak - 1 if current_streak < 0 else -1
                    user_info['loss'] += 1
                    user_info['role_stats'][played_role]['loss'] += 1
                    user_info['mmr'][played_role] = max(0, before_mmr - final_delta)
                    user_info['streak'] = new_streak
                    signed_delta = -final_delta
                user_info['role_stats'][played_role]['streak'] = role_streak
                update_peak_records(user_info)
                after_mmr = int(user_info['mmr'].get(played_role, 0) or 0)
                applied_deltas[uid_str] = final_delta
    
            match_players.append({
                "user_id": uid_str,
                "name": display_name,
                "team": "blue" if uid_str in game_state['blue'] else "red",
                "role": played_role,
                "result": "win" if is_win else "loss",
                "rating_source": rating_source,
                "delta": signed_delta,
                "delta_phase": f"노밴 {delta_phase}" if rating_source == "noban" else f"일반 {delta_phase}",
                "base_delta": final_delta,
                "before_mmr": before_mmr,
                "after_mmr": after_mmr,
            })
    
        rival_result_lines, rival_entries = await apply_rival_match_results(
            interaction,
            gid,
            game_state['blue'],
            game_state['red'],
            winner_ids,
        )
    
        bot.history.setdefault(gid, {})[queue_key] = {
            'match_id': match_id,
            'winner_ids': list(winner_ids),
            'loser_ids': list(loser_ids),
            'roles_map': dict(roles_map),
            'game_snapshot': dict(game_state),
            'pre_match_streaks': pre_match_streaks,
            'pre_role_streaks': pre_role_streaks,
            'pre_noban_stats': pre_noban_stats,
            'pre_rival_stats': pre_rival_stats,
            'rating_sources': dict(rating_sources),
            'applied_deltas': applied_deltas,
        }
        append_match_history(gid, {
            "id": match_id,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            "queue": queue_key,
            "mode": NOBAN_MODE_KEY,
            "winner": "blue" if is_blue_win else "red",
            "blue": list(game_state['blue']),
            "red": list(game_state['red']),
            "requested_prefs": game_state.get("requested_prefs", {}),
            "rival_matches": rival_entries,
            "players": match_players,
            "cancelled": False,
        })
    
        rival_birth_lines = refresh_auto_rivals(
            interaction.guild, gid, list(game_state['blue']) + list(game_state['red'])
        )
    
        if queue_keep:
            bot.active_games.setdefault(gid, {}).pop(queue_key, None)
            status_msg = "♻️ 큐 및 팀 조합은 유지됩니다."
        else:
            bot.queues.setdefault(gid, {})[queue_key] = []
            bot.active_games.setdefault(gid, {}).pop(queue_key, None)
            delete_participation_recruitment(gid, queue_key)
            set_start_wait_enabled(gid, queue_key, False)
            reset_wait_cleared = clear_reset_start_wait_after_match(gid, queue_key)
            touch_queue(gid, queue_key)
            status_msg = "🧹 노밴 모드 대기열과 진행 중인 팀 정보를 초기화했습니다."
            if reset_wait_cleared:
                status_msg += "\n▶️ 리셋 큐유지로 켜진 시작대기 모드를 자동 해제했습니다."
    
        schedule_participation_panel_refresh(gid, delay=0.2)
        record_winrate_reign_snapshot(gid)
        if not is_simulation:
            for player in match_players:
                if player.get("rating_source") != "noban":
                    await sync_registered_member_tier_role(interaction.guild, gid, player.get("user_id"))
            bot.save_lucid_data(gid)
    
        lines = []
        for player in match_players:
            result_icon = "▲" if player["result"] == "win" else "▼"
            source_label = "노밴 MMR" if player.get("rating_source") == "noban" else "일반 MMR"
            lines.append(
                f"{result_icon} <@{player['user_id']}> `[{player['role']}]` {source_label} "
                f"{get_public_mmr_rank(player['before_mmr'])} → {get_public_mmr_rank(player['after_mmr'])} ({player['delta']:+}점)"
            )
    
        embed = discord.Embed(
            title=f"🏆 {NOBAN_MODE_NAME} 결과 기록 완료",
            description=(
                f"승리팀: **{'블루' if is_blue_win else '레드'}팀**\n"
                f"{status_msg}"
            ),
            color=0x2ecc71,
        )
        embed.add_field(name="📊 노밴 기준 점수", value="\n".join(lines[:10]) or "기록 없음", inline=False)
        if rival_result_lines:
            embed.add_field(name="🔥 라이벌 매치 결과", value="\n".join(rival_result_lines[:10]), inline=False)
        if rival_birth_lines:
            embed.add_field(name="⚔️ 새로운 라이벌 탄생!", value="\n\n".join(rival_birth_lines[:5]), inline=False)
        embed.add_field(
            name="룰",
            value="노밴 MMR 보유자는 노밴 MMR만, 노밴 MMR이 없는 참가자는 선택 라인의 일반 MMR/승패가 변동됩니다.",
            inline=False,
        )
        await send_match_output(interaction, gid, embed=embed)
    
        try:
            await cleanup_vcs(interaction.guild, queue_key, game_state)
        except Exception as e:
            logger.warning(f"노밴 모드 음성 채널 정리 중 오류: {e}")
    
    async def publish_deferred_match_result(interaction, record=None):
        """Publish a ROFL result after its final AI-adjusted record is saved."""
        extras = getattr(interaction, "extras", None)
        pending = extras.get("lucid_pending_match_result") if isinstance(extras, dict) else None
        if not pending:
            return False
        try:
            if isinstance(record, dict):
                lines = []
                for player in record.get("players", []) or []:
                    before = int(player.get("before_mmr", 0) or 0)
                    after = int(player.get("after_mmr", 0) or 0)
                    delta = after - before
                    icon = "▲" if delta > 0 else "▼" if delta < 0 else "•"
                    lines.append(
                        f"{icon} <@{player.get('user_id')}> `[{player.get('role', '미지정')}]` {delta:+}점"
                    )
                embed = pending["embed"]
                for index, field in enumerate(embed.fields):
                    if field.name == "📊 점수 변동":
                        embed.set_field_at(index, name=field.name, value="\n".join(lines[:10]) or "기록 없음", inline=False)
                        break
            await pending["publish"]()
            return True
        finally:
            extras.pop("lucid_pending_match_result", None)


    async def process_classic_win(interaction, gid, 큐, 승리팀, 큐유지, game_state, *, retroactive=False):
        if game_state.get("mode") == NOBAN_MODE_KEY or 큐 == NOBAN_QUEUE_NUM:
            return await process_noban_win(interaction, gid, 큐, 승리팀, 큐유지, game_state)

        match_id = str(game_state.get("game_id") or f"{now_kst().strftime('%Y%m%d%H%M%S')}-q{큐}")
        game_state.setdefault("game_id", match_id)
        if has_match_history_id(gid, match_id):
            bot.active_games.setdefault(gid, {}).pop(큐, None)
            bot.save_lucid_data(gid)
            logger.warning("중복 일반 결과 요청 종료: guild_id=%s queue=%s match_id=%s", gid, 큐, match_id)
            await interaction.followup.send("⚠️ 이미 기록이 끝난 경기입니다. 중복 결과는 반영하지 않았습니다.")
            return {"DUPLICATE": True, "match_id": match_id}

        is_blue_win = 승리팀 in ['블루', 'blue', '1', '🔵']
        if not retroactive and not mark_match_result_processing(gid, game_state, "blue" if is_blue_win else "red"):
            logger.error("중단된 일반 결과 수동 복구 필요: guild_id=%s queue=%s match_id=%s", gid, 큐, match_id)
            await interaction.followup.send("⚠️ 이전 결과 처리가 중간에 중단된 경기입니다. 중복 MMR 방지를 위해 자동 재처리를 막았습니다. `/리셋` 전 로그와 경기 기록을 확인해주세요.")
            return {"RECOVERY_REQUIRED": True, "match_id": match_id}
        winner_ids = game_state['blue'] if is_blue_win else game_state['red']
        loser_ids = game_state['red'] if is_blue_win else game_state['blue']
        roles_map = game_state['roles']
        is_low_tier_match = game_state.get("mode") == LOW_TIER_MODE_KEY or 큐 == LOW_TIER_QUEUE_KEY
    
        bot.user_data.setdefault(gid, {})
        applied_deltas = {}
        pre_match_streaks = {}
        pre_role_streaks = {}
        pre_provisional_states = {}
        provisional_completion_lines = []
        pre_rival_stats = snapshot_rival_stats(gid, winner_ids + loser_ids)
        match_players = []
        announcements = []
        score_change_lines = []
        tier_change_lines = []
        match_status = {
            "MATCH_RESULT_COMMITTED": False,
            "NOTIFICATION_SENT": False,
            "VOICE_MOVED": False,
            "VOICE_CHANNELS_DELETED": False,
            "AUTO_REQUEUED": False,
        }

        async def run_safe_step(label, operation, status_key=None):
            try:
                result = operation()
                if inspect.isawaitable(result):
                    result = await result
            except Exception:
                logger.exception("경기 단계 실패: step=%s guild_id=%s queue=%s match_id=%s", label, gid, 큐, match_id)
                return None
            if status_key:
                match_status[status_key] = True
            return result
    
        # 팀 전력 보정은 경기 시작 전 원본 라인 MMR 스냅샷만 사용합니다.
        # 가중치(effective MMR)는 사용하지 않아 포지션 가중치와 난이도 보정이 중복되지 않게 합니다.
        pregame_team_scores = {"blue": [], "red": []}
        lineup_snapshot = game_state.get("lineup_mmr", {}) if isinstance(game_state.get("lineup_mmr"), dict) else {}
        for team_key, team_ids in (("blue", game_state.get("blue", [])), ("red", game_state.get("red", []))):
            for player_uid in team_ids:
                uid_key = str(player_uid)
                role = roles_map.get(uid_key)
                score = int(lineup_snapshot.get(uid_key, 0) or 0)
                if score <= 0 and role:
                    existing = bot.user_data.get(gid, {}).get(uid_key, {})
                    score = int((existing.get("mmr", {}) or {}).get(role, 0) or 0)
                if score > 0:
                    pregame_team_scores[team_key].append(score)
        pregame_blue_avg = (sum(pregame_team_scores["blue"]) / len(pregame_team_scores["blue"])) if pregame_team_scores["blue"] else 0
        pregame_red_avg = (sum(pregame_team_scores["red"]) / len(pregame_team_scores["red"])) if pregame_team_scores["red"] else 0
        
        for uid_str in (winner_ids + loser_ids):
            member = interaction.guild.get_member(int(uid_str))
            if not member:
                try:
                    member = await interaction.guild.fetch_member(int(uid_str))
                except discord.NotFound:
                    member = None
                except discord.HTTPException:
                    member = None
    
            display_name = member.display_name if member else f"UID {uid_str}"
            mention_text = member.mention if member else f"<@{uid_str}>"
    
            if uid_str not in bot.user_data[gid]:
                bot.user_data[gid][uid_str] = {
                    'mmr': {r:0 for r in ROLES}, 
                    'plays': {r:0 for r in ROLES}, 
                    'eval_scores': {r: [] for r in ROLES}, 
                    'win': 0, 
                    'loss': 0, 
                    'streak': 0,
                    'lol_name': display_name
                }
                
            ud = ensure_user_format(bot.user_data[gid][uid_str])
            played_role = roles_map.get(uid_str)
            
            if not played_role: 
                continue 
                
            pre_match_streaks[uid_str] = ud.get('streak', 0)
            ud['role_stats'].setdefault(played_role, {'win': 0, 'loss': 0, 'streak': 0})
            pre_role_streaks[uid_str] = int(ud['role_stats'][played_role].get('streak', 0) or 0)
            before_mmr = ud['mmr'].get(played_role, 0)
            old_tier_name = get_tier_name(before_mmr)
            old_tier_rank = get_tier_rank_label(before_mmr)
            
            current_plays = ud['plays'][played_role]
            provisional_state = get_provisional_mmr_state(ud)
            pre_provisional_states[uid_str] = copy.deepcopy(provisional_state)
            if is_low_tier_match:
                base_delta, delta_phase = get_low_tier_match_delta_config(gid, current_plays)
            else:
                base_delta, delta_phase = get_role_match_delta_config(gid, current_plays)
            base_delta, delta_phase, used_provisional = apply_provisional_base_delta(
                gid,
                ud,
                base_delta,
                delta_phase,
                role=played_role,
                is_low_tier=is_low_tier_match,
                retroactive=retroactive,
            )
            ud['plays'][played_role] += 1
            ud['role_stats'].setdefault(played_role, {'win': 0, 'loss': 0})
            
            current_streak = int(ud.get('streak', 0) or 0)
            current_role_streak = int(ud['role_stats'][played_role].get('streak', 0) or 0)
            
            is_win = uid_str in winner_ids
            player_team = "blue" if uid_str in game_state['blue'] else "red"
            team_adjustment = 0
            if is_win:
                if is_low_tier_match:
                    new_streak = current_streak
                    final_delta = base_delta
                else:
                    team_adjustment = get_player_team_delta_adjustment(
                        player_team, True, pregame_blue_avg, pregame_red_avg
                    )
                    rating_result = shared_lol.calculate_classic_rating_result(
                        before_mmr,
                        base_delta,
                        current_role_streak,
                        True,
                        team_adjustment,
                        streak_adjustment_fn=shared_lol.get_streak_adjustment,
                    )
                    role_streak = rating_result["streak"]
                    new_streak = current_streak + 1 if current_streak > 0 else 1
                    final_delta = rating_result["magnitude"]
                
                ud['win'] += 1
                ud['role_stats'][played_role]['win'] += 1
                ud['mmr'][played_role] += final_delta
                ud['streak'] = new_streak
                if not is_low_tier_match:
                    ud['role_stats'][played_role]['streak'] = role_streak
                
            else:
                if is_low_tier_match:
                    new_streak = current_streak
                    final_delta = base_delta
                else:
                    team_adjustment = get_player_team_delta_adjustment(
                        player_team, False, pregame_blue_avg, pregame_red_avg
                    )
                    rating_result = shared_lol.calculate_classic_rating_result(
                        before_mmr,
                        base_delta,
                        current_role_streak,
                        False,
                        team_adjustment,
                        streak_adjustment_fn=shared_lol.get_streak_adjustment,
                    )
                    role_streak = rating_result["streak"]
                    new_streak = current_streak - 1 if current_streak < 0 else -1
                    final_delta = rating_result["magnitude"]
                
                ud['loss'] += 1
                ud['role_stats'][played_role]['loss'] += 1
                ud['mmr'][played_role] = max(0, ud['mmr'][played_role] - final_delta)
                ud['streak'] = new_streak
                if not is_low_tier_match:
                    ud['role_stats'][played_role]['streak'] = role_streak
                
            update_peak_records(ud)
            applied_deltas[uid_str] = final_delta
            signed_delta = final_delta if uid_str in winner_ids else -final_delta
            match_players.append({
                "user_id": uid_str,
                "name": display_name,
                "team": "blue" if uid_str in game_state['blue'] else "red",
                "role": played_role,
                "result": "win" if uid_str in winner_ids else "loss",
                "lineup_mmr": int(game_state.get("lineup_mmr", {}).get(uid_str, before_mmr)),
                "delta": signed_delta,
                "delta_phase": delta_phase,
                "base_delta": base_delta,
                "team_mmr_adjustment": int(team_adjustment),
                "provisional_mmr": bool(used_provisional),
                "provisional_role": played_role if used_provisional else None,
                "provisional_base_delta": int(base_delta) if used_provisional else 0,
                "before_mmr": before_mmr,
                "after_mmr": ud['mmr'].get(played_role, 0)
            })
                
            new_mmr = ud['mmr'].get(played_role, 0)
            new_tier_name = get_tier_name(new_mmr)
            new_tier_rank = get_tier_rank_label(new_mmr)
            
            before_rank_points = format_profile_mmr_points(
                before_mmr, interaction.guild, gid, with_emoji=False
            )
            after_rank_points = format_profile_mmr_points(
                new_mmr, interaction.guild, gid, with_emoji=False
            )
    
            if old_tier_rank != new_tier_rank and TIER_DATA.get(new_tier_name):
                emoji_tag = get_tier_emoji(new_tier_name, interaction.guild, gid)
                direction = "승급" if int(new_mmr or 0) > int(before_mmr or 0) else "강등"
                tier_change_lines.append(
                    f"{emoji_tag} {mention_text} **{direction}** · "
                    f"`{before_rank_points}` ➡️ **{after_rank_points}**"
                )
    
            result_icon = "▲" if uid_str in winner_ids else "▼"
            # Keep the public score list compact.  Tier transitions retain
            # the before/after detail in the dedicated field above.
            score_change_lines.append(f"{result_icon} {mention_text} {signed_delta:+}점")
    
            if used_provisional:
                advanced, completed, provisional_games, provisional_target = advance_provisional_mmr(gid, ud, played_role)
                if advanced and completed:
                    provisional_completion_lines.append(
                        f"✅ {mention_text} **{played_role}** 임시배치 완료 · **{provisional_games}/{provisional_target}경기**"
                    )
    
        team_before_scores = {"blue": [], "red": []}
        players_by_team_role = {}
        for record in match_players:
            team = record.get("team")
            role = record.get("role")
            before_score = record.get("before_mmr", 0)
            if team in team_before_scores:
                team_before_scores[team].append(before_score)
                players_by_team_role[(team, role)] = record
    
        team_before_avg = {
            team: (sum(scores) / len(scores)) if scores else 0
            for team, scores in team_before_scores.items()
        }
    
        for record in match_players:
            uid_str = record.get("user_id")
            team = record.get("team")
            role = record.get("role")
            opponent_team = "red" if team == "blue" else "blue"
            opponent = players_by_team_role.get((opponent_team, role))
            if not opponent or uid_str not in bot.user_data.get(gid, {}):
                continue
    
            user_info = ensure_user_format(bot.user_data[gid][uid_str])
            underdog = user_info["underdog_stats"]
            mmr_gap = opponent.get("before_mmr", 0) - record.get("before_mmr", 0)
            is_win = record.get("result") == "win"
    
            if mmr_gap > 0:
                underdog["lane_deficit_games"] += 1
                if mmr_gap >= TITLE_MMR_FIRST_UNDERVALUED_GAP:
                    underdog["first_undervalued_games_v2"] += 1
                    if is_win:
                        underdog["first_undervalued_wins_v2"] += 1
                if mmr_gap >= TITLE_MMR_SCORE_IS_EXTRA_GAP:
                    underdog["lane_deficit_score_games"] += 1
                    if is_win:
                        underdog["lane_deficit_score_wins"] += 1
                if is_win:
                    underdog["lane_deficit_wins"] += 1
                    if mmr_gap >= TITLE_MMR_COST_EFFECTIVE_GAP:
                        underdog["lane_deficit_cost_wins"] += 1
                    if mmr_gap >= TITLE_MMR_UNDERDOG_GAP:
                        underdog["lane_deficit_200_wins"] += 1
                    if mmr_gap >= TITLE_MMR_PEAK_GAP:
                        underdog["lane_deficit_300_wins"] += 1
                    if mmr_gap >= TITLE_MMR_FIRST_GIANT_SLAYER_GAP:
                        underdog["first_giant_slayer_wins_v2"] += 1
    
            team_gap = team_before_avg.get(opponent_team, 0) - team_before_avg.get(team, 0)
            if is_win and team_gap >= TITLE_MMR_TEAM_DEFICIT_GAP:
                underdog["team_deficit_150_wins"] += 1
            if is_win and team_gap >= TITLE_MMR_FIRST_TEAM_DEFICIT_GAP:
                underdog["first_team_deficit_wins_v2"] += 1
    
        for uid_str in (winner_ids + loser_ids):
            if uid_str in bot.user_data.get(gid, {}):
                await run_safe_step(
                    "classic_title",
                    lambda uid=uid_str: check_classic_title_unlocks(interaction, gid, uid),
                )
    
        rival_result = await run_safe_step(
            "rival_results",
            lambda: apply_rival_match_results(
                interaction,
                gid,
                game_state['blue'],
                game_state['red'],
                winner_ids,
            ),
        )
        rival_result_lines, rival_entries = rival_result or ([], [])
    
        bot.history.setdefault(gid, {})[큐] = {
            'match_id': match_id,
            'winner_ids': list(winner_ids),
            'loser_ids': list(loser_ids),
            'roles_map': dict(roles_map),
            'game_snapshot': dict(game_state),
            'pre_match_streaks': pre_match_streaks,
            'pre_role_streaks': pre_role_streaks,
            'pre_provisional_states': pre_provisional_states,
            'pre_rival_stats': pre_rival_stats,
            'applied_deltas': applied_deltas
        }
        append_match_history(gid, {
            "id": match_id,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            "queue": 큐,
            "mode": LOW_TIER_MODE_KEY if is_low_tier_match else "classic",
            "winner": "blue" if is_blue_win else "red",
            "blue": list(game_state['blue']),
            "red": list(game_state['red']),
            "requested_prefs": game_state.get("requested_prefs", {}),
            "rival_matches": rival_entries,
            "players": match_players,
            "cancelled": False
        })
    
        rival_birth_lines = await run_safe_step(
            "rival_refresh",
            lambda: refresh_auto_rivals(
                interaction.guild, gid, list(game_state['blue']) + list(game_state['red'])
            ),
        ) or []
    
        if is_low_tier_match:
            for uid_str in (winner_ids + loser_ids):
                if uid_str in bot.user_data.get(gid, {}):
                    await run_safe_step(
                        "low_tier_title",
                        lambda uid=uid_str: check_low_tier_title_unlocks(interaction, gid, uid),
                    )
    
        update_duo_stats_for_team(gid, list(winner_ids), True)
        update_duo_stats_for_team(gid, list(loser_ids), False)
    
        for uid_str in (winner_ids + loser_ids):
            if uid_str in bot.user_data.get(gid, {}):
                await run_safe_step(
                    "duo_title",
                    lambda uid=uid_str: check_duo_title_unlocks(interaction, gid, uid),
                )
    
        auto_requeue = False
        if retroactive:
            status_msg = "🕰️ ROFL 소급 경기로 전적/MMR만 반영했습니다. 현재 대기열과 진행 중인 게임은 건드리지 않았습니다."
        elif 큐유지:
            if 큐 in bot.active_games[gid]: 
                del bot.active_games[gid][큐]
            status_msg = "♻️ 큐 및 팀 조합은 유지되며, 대기열이 10명인 경우 자동으로 다음 매치를 시도합니다."
            auto_requeue = len(bot.queues.get(gid, {}).get(큐, [])) == 10
        else:
            bot.queues[gid][큐] = []
            if 큐 in bot.active_games[gid]:
                del bot.active_games[gid][큐]
            await run_safe_step(
                "recruitment_cleanup",
                lambda: delete_participation_recruitment(gid, 큐),
            )
            await run_safe_step(
                "start_wait_cleanup",
                lambda: set_start_wait_enabled(gid, 큐, False),
            )
            reset_wait_cleared = await run_safe_step(
                "reset_start_wait_cleanup",
                lambda: clear_reset_start_wait_after_match(gid, 큐),
            ) or False
            await run_safe_step(
                "queue_touch",
                lambda: touch_queue(gid, 큐),
            )
            # Queue cleanup is an internal operation.  Keep it out of the
            # public result card; the result itself is the user-facing state.
            status_msg = ""

        record_winrate_reign_snapshot(gid)
        save_result = bot.save_lucid_data(gid)
        if save_result is False:
            logger.error(
                "경기 핵심 결과 저장 실패: guild_id=%s queue=%s match_id=%s",
                gid,
                큐,
                match_id,
            )
            raise RuntimeError("경기 결과 핵심 저장에 실패했습니다.")
        match_status["MATCH_RESULT_COMMITTED"] = True
        logger.info(
            "경기 핵심 결과 commit 완료: guild_id=%s queue=%s match_id=%s",
            gid,
            큐,
            match_id,
        )

        for uid_str in (winner_ids + loser_ids):
            if uid_str not in bot.user_data.get(gid, {}):
                continue
            if is_low_tier_match:
                await run_safe_step(
                    "low_tier_role_sync",
                    lambda uid=uid_str: sync_registered_member_tier_role(interaction.guild, gid, uid),
                )
            await run_safe_step(
                "role_sync",
                lambda uid=uid_str: sync_registered_member_tier_role(interaction.guild, gid, uid),
            )
    
        # 경기 종료 직후 Discord 참가 패널도 현재 큐 상태와 맞춥니다.
        # 예전에는 내부 큐는 비었지만 패널 메시지가 10/10으로 남는 경로가 있었습니다.
        if not retroactive:
            await run_safe_step(
                "participation_panel_refresh",
                lambda: schedule_participation_panel_refresh(gid, delay=0.2),
            )
    
        embed = discord.Embed(
            title=f"🏆 {get_queue_label(큐)} 큐 매치 기록완료", 
            description=(
                f"승리팀: **{'블루' if is_blue_win else '레드'}팀**"
                + (f"\n{status_msg}" if status_msg else "")
            ), 
            color=0x2ecc71
        )
        if provisional_completion_lines:
            embed.add_field(
                name="🟡 임시배치",
                value="\n".join(provisional_completion_lines[:10]),
                inline=False,
            )
        if tier_change_lines: 
            embed.add_field(name="🎊 승급 / 강등 안내", value="\n".join(tier_change_lines), inline=False)
    
        # Rival details are sent as a separate short notice below.  Keeping
        # them out of this card prevents score/latest-winner metadata from
        # leaking into the compact result UI.
        embed.add_field(
            name="📊 점수 변동",
            value="\n".join(score_change_lines[:10]) if score_change_lines else "기록 없음",
            inline=False
        )
        if retroactive:
            notify = lambda: interaction.followup.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            notify = lambda: send_match_output(interaction, gid, embed=embed)
        interaction_extras = getattr(interaction, "extras", None)
        if isinstance(interaction_extras, dict) and interaction_extras.get("lucid_defer_match_result"):
            interaction_extras["lucid_pending_match_result"] = {
                "embed": embed,
                "publish": lambda: run_safe_step("notification", notify, "NOTIFICATION_SENT"),
            }
        else:
            await run_safe_step("notification", notify, "NOTIFICATION_SENT")

        def _build_rival_notice_lines(entries):
            """Return compact rival result lines without score/latest metadata."""
            lines = []
            seen = set()
            winner_set = {str(uid) for uid in winner_ids}
            for item in entries or []:
                if not isinstance(item, dict):
                    continue
                uid = str(item.get("uid") or "")
                rival_uid = str(item.get("rival_uid") or "")
                if not uid or not rival_uid:
                    continue
                pair = tuple(sorted((uid, rival_uid)))
                if pair in seen:
                    continue
                seen.add(pair)
                left_label = get_member_label(interaction.guild, gid, pair[0])
                right_label = get_member_label(interaction.guild, gid, pair[1])
                winner_uid = pair[0] if pair[0] in winner_set else pair[1] if pair[1] in winner_set else None
                winner_line = (
                    f"🏆 {get_member_label(interaction.guild, gid, winner_uid)} 승리"
                    if winner_uid else ""
                )
                record_uid = winner_uid or uid
                raw = bot.user_data.get(gid, {}).get(record_uid, {})
                stats = raw.get("rival_stats", {}) if isinstance(raw, dict) else {}
                record_line = ""
                if isinstance(stats, dict):
                    wins = int(stats.get("wins", 0) or 0)
                    losses = int(stats.get("losses", 0) or 0)
                    record_line = f"{get_member_label(interaction.guild, gid, record_uid)} 기준 · 라이벌 전적 {wins}승 {losses}패"
                lines.append(
                    f"{left_label} 🆚 {right_label}"
                    + (f"\n{winner_line}" if winner_line else "")
                    + (f"\n{record_line}" if record_line else "")
                )
            return lines

        rival_notice_lines = _build_rival_notice_lines(rival_entries)
        if rival_notice_lines:
            await run_safe_step(
                "rival_notification",
                lambda: send_match_output(
                    interaction,
                    gid,
                    content="🔥 **라이벌 매치 결과**\n\n" + "\n\n".join(rival_notice_lines[:10]),
                    allowed_mentions=discord.AllowedMentions.none(),
                    notify=False,
                ),
            )

        if rival_birth_lines:
            # refresh_auto_rivals retains the historical detailed string for
            # storage/other callers.  Only the first (pair-name) line is
            # exposed here so rival score metadata never reaches this UI.
            birth_notice_lines = []
            for raw_line in rival_birth_lines[:5]:
                first_line = str(raw_line or "").splitlines()[0].strip()
                if first_line:
                    birth_notice_lines.append(first_line)
            if birth_notice_lines:
                await run_safe_step(
                    "rival_birth_notification",
                    lambda: send_match_output(
                        interaction,
                        gid,
                        content="⚔️ **새로운 라이벌 탄생!**\n\n" + "\n\n".join(birth_notice_lines),
                        allowed_mentions=discord.AllowedMentions.none(),
                        notify=False,
                    ),
                )
    
        if not retroactive:
            # Move the actual 10 match participants by user ID first.
            # Previously cleanup_vcs only moved members found inside voice
            # channels with an exact expected channel name, so a renamed/
            # stale/team channel could leave everyone behind even though
            # the match result itself was recorded successfully.
            participant_ids = list(game_state.get("blue", [])) + list(game_state.get("red", []))
            moved_count = await run_safe_step(
                "voice_move",
                lambda: move_members_to_waiting_voice(
                    interaction.guild,
                    participant_ids,
                    waiting_channel_id=(game_state.get("voice_channels") or {}).get("waiting"),
                ),
                "VOICE_MOVED",
            )
            if moved_count is not None:
                logger.info(
                    "경기 종료 대기실 이동 완료: guild_id=%s queue=%s moved=%s/%s",
                    gid,
                    큐,
                    moved_count,
                    len(set(map(str, participant_ids))),
                )
            await run_safe_step(
                "voice_cleanup",
                lambda: cleanup_vcs(interaction.guild, 큐, game_state),
                "VOICE_CHANNELS_DELETED",
            )
    
        if auto_requeue and not retroactive:
            await run_safe_step(
                "auto_requeue",
                lambda: internal_lineup(interaction, 큐),
                "AUTO_REQUEUED",
            )

        return match_status
    
    # `/리플레이기록취소`에서 호출합니다.
    async def undo_record(interaction: discord.Interaction, 큐: str):
        _sync_runtime()
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        queue_key = normalize_queue_selector(큐)
        if queue_key is None:
            return await interaction.response.send_message(f"⚠️ 큐는 `1~5`, `노밴 모드`, `저티어 큐`, `아레나(3x6)`, `협곡 리그전`, `칼바람 나락`, `칼바람 리그전` 중에서 선택해주세요.", ephemeral=True)
        feature_key = get_queue_feature_key(queue_key)
        if feature_key and not is_feature_enabled(gid, feature_key):
            return await interaction.response.send_message(get_disabled_feature_message(feature_key), ephemeral=True)
    
        hist = bot.history.get(gid, {}).get(queue_key)
        
        if not hist:
            return await interaction.response.send_message(
                f"❌ 해당 {get_queue_label(queue_key)} 큐 세션에 롤백을 진행할 백업 매치 스냅샷이 존재하지 않습니다.", 
                ephemeral=True
            )
        
        winner_ids = hist['winner_ids']
        loser_ids = hist['loser_ids']
        roles_map = hist['roles_map']
        tier_restores = []
        is_noban_history = hist.get('game_snapshot', {}).get('mode') == NOBAN_MODE_KEY
        
        if is_noban_history:
            rating_sources = hist.get('rating_sources', {})
            pre_noban_stats = hist.get('pre_noban_stats', {})
            applied_deltas = hist.get('applied_deltas', {})
            for uid_str in (winner_ids + loser_ids):
                if uid_str not in bot.user_data.get(gid, {}):
                    continue
    
                ud = ensure_user_format(bot.user_data[gid][uid_str])
                played_role = roles_map.get(uid_str)
                source = rating_sources.get(uid_str) or get_noban_rating_source(ud, played_role)
                if source == "noban":
                    snapshot = pre_noban_stats.get(uid_str)
                    if snapshot:
                        ud['noban_mmr'] = int(snapshot.get('mmr', get_noban_mmr(ud)) or 0)
                        ud.setdefault('noban_stats', {})['win'] = int(snapshot.get('win', 0) or 0)
                        ud.setdefault('noban_stats', {})['loss'] = int(snapshot.get('loss', 0) or 0)
                else:
                    if not played_role:
                        continue
                    exact_delta = int(applied_deltas.get(uid_str, 0) or 0)
                    ud['plays'][played_role] = max(0, int(ud['plays'].get(played_role, 0) or 0) - 1)
                    ud['streak'] = hist.get('pre_match_streaks', {}).get(uid_str, 0)
                    ud['role_stats'].setdefault(played_role, {'win': 0, 'loss': 0})
                    if uid_str in hist.get('pre_role_streaks', {}):
                        ud['role_stats'][played_role]['streak'] = hist['pre_role_streaks'][uid_str]
                    if uid_str in winner_ids:
                        ud['win'] = max(0, int(ud.get('win', 0) or 0) - 1)
                        ud['role_stats'][played_role]['win'] = max(0, int(ud['role_stats'][played_role].get('win', 0) or 0) - 1)
                        ud['mmr'][played_role] = max(0, int(ud['mmr'].get(played_role, 0) or 0) - exact_delta)
                    else:
                        ud['loss'] = max(0, int(ud.get('loss', 0) or 0) - 1)
                        ud['role_stats'][played_role]['loss'] = max(0, int(ud['role_stats'][played_role].get('loss', 0) or 0) - 1)
                        ud['mmr'][played_role] = int(ud['mmr'].get(played_role, 0) or 0) + exact_delta
    
        else:
            for uid_str in (winner_ids + loser_ids):
                if uid_str not in bot.user_data.get(gid, {}): 
                    continue
                    
                ud = ensure_user_format(bot.user_data[gid][uid_str])
                old_tier_name = get_tier_name(get_avg_mmr(ud['mmr']))
                played_role = roles_map.get(uid_str)
                
                if not played_role: 
                    continue
                
                ud['plays'][played_role] = max(0, ud['plays'][played_role] - 1)
                
                pre_provisional = hist.get('pre_provisional_states', {}).get(uid_str)
                if isinstance(pre_provisional, dict):
                    ud[PROVISIONAL_MMR_KEY] = dict(pre_provisional)
    
                exact_delta = hist['applied_deltas'].get(uid_str, 20)
                ud['streak'] = hist['pre_match_streaks'].get(uid_str, 0)
                if uid_str in hist.get('pre_role_streaks', {}):
                    ud['role_stats'][played_role]['streak'] = hist['pre_role_streaks'][uid_str]
                
                if uid_str in winner_ids:
                    ud['win'] = max(0, ud['win'] - 1)
                    ud['role_stats'].setdefault(played_role, {'win': 0, 'loss': 0})
                    ud['role_stats'][played_role]['win'] = max(0, int(ud['role_stats'][played_role].get('win', 0) or 0) - 1)
                    ud['mmr'][played_role] = max(0, ud['mmr'][played_role] - exact_delta)
                else:
                    ud['loss'] = max(0, ud['loss'] - 1)
                    ud['role_stats'].setdefault(played_role, {'win': 0, 'loss': 0})
                    ud['role_stats'][played_role]['loss'] = max(0, int(ud['role_stats'][played_role].get('loss', 0) or 0) - 1)
                    ud['mmr'][played_role] += exact_delta
                    
                new_tier_name = get_tier_name(get_avg_mmr(ud['mmr']))
                member = interaction.guild.get_member(int(uid_str))
                
                if member and old_tier_name != new_tier_name:
                    restore_emoji = get_tier_emoji(new_tier_name, interaction.guild, gid)
                    tier_restores.append(f"{restore_emoji} **{member.mention}** 티어가 복구되었습니다. (`{old_tier_name}` -> `{new_tier_name}`)")
    
        restore_rival_stats(gid, hist.get('pre_rival_stats', {}))
    
        bot.active_games.setdefault(gid, {})[queue_key] = hist['game_snapshot']
        mark_match_history_cancelled(gid, hist.get('match_id'))
    
        record_winrate_reign_snapshot(gid)
        bot.save_lucid_data(gid)
        del bot.history[gid][queue_key]
    
        embed = discord.Embed(
            title=f"⏪ {get_queue_label(queue_key)} 큐 기록 취소 완료", 
            color=0xe74c3c
        )
        if is_noban_history:
            embed.description = (
                "**노밴 모드 기록을 취소했습니다.**\n\n"
                "참가 당시 사용한 점수 출처에 따라 노밴 MMR 또는 일반 라인 MMR/승패를 되돌렸습니다.\n"
                "당시 매치 팀 조합 데이터가 다시 로드되었습니다."
            )
        else:
            embed.description = (
                "**최근 경기 정산을 취소했습니다.**\n\n"
                "점수, 전적, 연승 기록을 되돌렸고 당시 팀 정보도 다시 불러왔습니다.\n"
                "올바른 진영으로 `/승리`를 다시 입력해주세요."
            )
        
        if tier_restores: 
            embed.add_field(name="티어 복구", value="\n".join(tier_restores), inline=False)
            
        if queue_key == LEAGUE_QUEUE_KEY:
            await send_league_output(interaction, gid, embed=embed)
        elif interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)
    
    
    @bot.tree.command(name="리셋", description="[내전 관리자] 특정 큐 번호의 활성화된 세션 및 대기 데이터와 음성 채널을 강제 삭제합니다.")
    @app_commands.choices(큐=reset_queue_choices)
    @app_commands.describe(큐유지="대기열 인원을 유지하고 시작대기 상태로 되돌립니다.")
    async def q_reset(interaction: discord.Interaction, 큐: str, 큐유지: bool = False):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        queue_key = normalize_queue_selector(큐)
        if queue_key is None:
            return await interaction.response.send_message(f"⚠️ 큐는 `1~5`, `노밴 모드`, `저티어 큐`, `아레나(3x6)`, `협곡 리그전`, `칼바람 나락`, `칼바람 리그전` 중에서 선택해주세요.", ephemeral=True)
        feature_key = get_queue_feature_key(queue_key)
        if feature_key and not is_feature_enabled(gid, feature_key):
            return await interaction.response.send_message(get_disabled_feature_message(feature_key), ephemeral=True)
        active_state_for_reset = bot.active_games.get(gid, {}).get(queue_key)
        is_simulation_reset = queue_key in (LEAGUE_SIM_QUEUE_KEY, LEAGUE_SERIES_SIM_QUEUE_KEY)
        if is_simulation_reset:
            큐유지 = False
        if 큐유지 and queue_key == LEAGUE_QUEUE_KEY:
            if not active_state_for_reset:
                return await interaction.response.send_message(f"⚠️ 큐유지 리셋할 진행 중인 {LEAGUE_MODE_NAME}이 없습니다.", ephemeral=True)
            matches = active_state_for_reset.get("matches", {}) or {}
            if any((match or {}).get("winner") for match in matches.values()):
                return await interaction.response.send_message(
                    f"⚠️ 이미 결과가 기록된 {LEAGUE_MODE_NAME}은 큐유지 리셋할 수 없습니다. 기록 꼬임 방지를 위해 `/리셋 큐:{LEAGUE_MODE_NAME}` 으로 완전 초기화만 가능합니다.",
                    ephemeral=True
                )
    
        operation_key = bot.begin_admin_operation(gid, f"reset:{queue_key}")
        if not operation_key:
            return await reject_duplicate_admin_operation(interaction, f"{get_queue_label(queue_key)} 리셋")
    
        await interaction.response.defer(ephemeral=True)
        try:
            queues = ensure_guild_queues(gid)
            active_state = bot.active_games.get(gid, {}).get(queue_key)
            has_reset_target = bool(active_state) or bool(queues.get(queue_key)) or queue_key in queues
            if has_reset_target:
                kept_count = len(queues.get(queue_key, []))
                missing_count = 0
                if 큐유지 and active_state:
                    if queue_key == LEAGUE_QUEUE_KEY and active_state.get("queue_snapshot"):
                        restored_entries = []
                        missing_count = 0
                        for entry in active_state.get("queue_snapshot", [])[:LEAGUE_PLAYER_COUNT]:
                            user, _, pref1, pref2, pref3 = normalize_queue_entry(entry)
                            member = interaction.guild.get_member(int(user.id))
                            if not member:
                                try:
                                    member = await interaction.guild.fetch_member(int(user.id))
                                except (discord.NotFound, discord.HTTPException, ValueError):
                                    member = None
                            if not member:
                                missing_count += 1
                                continue
                            restored_entries.append([member, time.time(), pref1, pref2, pref3])
                        queues[queue_key] = restored_entries
                        kept_count = len(restored_entries)
                    elif active_state.get("teams"):
                        previous_ids = []
                        for team in active_state.get("teams", []):
                            previous_ids.extend(team.get("players", []))
                        previous_ids = list(dict.fromkeys(str(uid) for uid in previous_ids))
                        if previous_ids:
                            roles_map = active_state.get("roles", {})
                            requested_prefs = active_state.get("requested_prefs", {})
                            forced_ids = set(str(uid) for uid in active_state.get("low_tier_forced_ids", []))
                            restored_entries = []
                            for uid in previous_ids:
                                member = interaction.guild.get_member(int(uid))
                                if not member:
                                    try:
                                        member = await interaction.guild.fetch_member(int(uid))
                                    except (discord.NotFound, discord.HTTPException):
                                        member = None
    
                                if not member:
                                    missing_count += 1
                                    continue
    
                                prefs = list(requested_prefs.get(uid, [roles_map.get(uid), None, None]))
                                prefs = (prefs + [None, None, None])[:3]
                                entry = [member, time.time(), prefs[0], prefs[1], prefs[2]]
                                if queue_key == LOW_TIER_QUEUE_KEY and uid in forced_ids:
                                    entry.append("force_lowtier")
                                restored_entries.append(entry)
                            queues[queue_key] = restored_entries
                            kept_count = len(restored_entries)
                    else:
                        previous_ids = list(active_state.get("blue", [])) + list(active_state.get("red", []))
                        previous_ids = list(dict.fromkeys(str(uid) for uid in previous_ids))
                        if previous_ids:
                            roles_map = active_state.get("roles", {})
                            requested_prefs = active_state.get("requested_prefs", {})
                            forced_ids = set(str(uid) for uid in active_state.get("low_tier_forced_ids", []))
                            restored_entries = []
                            for uid in previous_ids:
                                member = interaction.guild.get_member(int(uid))
                                if not member:
                                    try:
                                        member = await interaction.guild.fetch_member(int(uid))
                                    except (discord.NotFound, discord.HTTPException):
                                        member = None
    
                                if not member:
                                    missing_count += 1
                                    continue
    
                                prefs = list(requested_prefs.get(uid, [roles_map.get(uid), None, None]))
                                prefs = (prefs + [None, None, None])[:3]
                                entry = [member, time.time(), prefs[0], prefs[1], prefs[2]]
                                if queue_key == LOW_TIER_QUEUE_KEY and uid in forced_ids:
                                    entry.append("force_lowtier")
                                restored_entries.append(entry)
                            queues[queue_key] = restored_entries
                            kept_count = len(restored_entries)
    
                if gid in bot.active_games and queue_key in bot.active_games[gid]: 
                    del bot.active_games[gid][queue_key]
                if gid in bot.history and queue_key in bot.history[gid]: 
                    del bot.history[gid][queue_key]
                    
                await cleanup_vcs(interaction.guild, queue_key, active_state_for_reset)
                if 큐유지:
                    if queue_key != LEAGUE_QUEUE_KEY:
                        set_start_wait_enabled(gid, queue_key, True)
                        set_reset_start_wait_enabled(gid, queue_key, True)
                    touch_queue(gid, queue_key)
                    required = get_required_count(queue_key)
                    next_step = (
                        f"2. 준비가 끝나면 `/협곡리그전팀구성` 으로 다시 대진표를 생성하세요."
                        if queue_key == LEAGUE_QUEUE_KEY else
                        f"2. 준비가 끝나면 `/내전진행 작업:시작 큐:{get_queue_label(queue_key)}` 으로 다시 시작하세요."
                    )
                    reset_status = (
                        "현재 상태: `협곡 리그전 재구성 대기`\n"
                        if queue_key == LEAGUE_QUEUE_KEY else
                        "현재 상태: `⏸️ 시작대기 ON`\n"
                    )
                    reset_message = (
                        f"♻️ **{get_queue_label(queue_key)} 큐유지 리셋 완료**\n"
                        "대기열 인원은 유지하고, 팀/음성/진행 상태만 초기화했습니다.\n"
                        f"{reset_status}"
                        f"현재 인원: `{kept_count}/{required}`\n"
                        + (f"불러오지 못한 인원: `{missing_count}`명\n" if missing_count else "")
                        + "\n**다음 단계**\n"
                        + "1. 필요하면 `/포지션변경`, `/강제퇴장`, `/강제참가`로 대기열을 조정하세요.\n"
                        + next_step
                    )
                    if queue_key == LEAGUE_QUEUE_KEY:
                        await send_league_output(interaction, gid, content=reset_message)
                    else:
                        await interaction.followup.send(reset_message, ephemeral=True)
                else:
                    queues[queue_key] = []
                    clear_reset_start_wait_after_match(gid, queue_key)
                    bot.queue_updated_at.setdefault(gid, {}).pop(queue_key, None)
                    bot.save_lucid_data(gid)
                    schedule_participation_panel_refresh(gid, delay=0.2)
                    reset_message = f"♻️ 시스템에 의해 {get_queue_label(queue_key)} 대기열 및 팀 생성 구조가 포맷 초기화되었습니다."
                    if queue_key == LEAGUE_QUEUE_KEY:
                        await send_league_output(interaction, gid, content=reset_message)
                    else:
                        await interaction.followup.send(reset_message, ephemeral=True)
            else:
                await interaction.followup.send("⚠️ 유효한 대상 채널 범주에 매칭되는 데이터가 없습니다.", ephemeral=True)
        finally:
            bot.finish_admin_operation(operation_key)
    
    @app_commands.describe(
        작업="실행할 복구 작업",
        유저="대상 유저가 필요한 작업에서 선택합니다.",
        큐="경기기록취소에서 되돌릴 큐입니다.",
        라인="라인 전적 또는 전적 보정 대상 라인입니다.",
        순번="최근 몇 번째 경기인지 선택합니다.",
        챔피언="상세스탯수정/상세데이터삭제에서 대상 챔피언입니다.",
        번호="상세데이터삭제에서 삭제할 목록 번호입니다.",
        킬="상세스탯수정에서 킬을 수정할 때 입력합니다.",
        데스="상세스탯수정에서 데스를 수정할 때 입력합니다.",
        어시="상세스탯수정에서 어시스트를 수정할 때 입력합니다.",
        딜량="상세스탯수정에서 딜량을 수정할 때 입력합니다.",
        경기시간="상세스탯수정에서 경기 시간을 MM:SS 형식으로 입력합니다.",
        스샷소환사명="상세스탯수정에서 스크린샷에 표시된 소환사명을 남깁니다.",
        적용="자동/추정 보정에서 실제 적용 여부입니다.",
        승="라인전적보정에서 설정할 승수입니다.",
        패="라인전적보정에서 설정할 패수입니다.",
        판수도맞춤="라인전적보정에서 승+패로 판수도 맞춥니다.",
        시작점수="라인전적추정보정에서 기준 시작 MMR입니다.",
        mmr변동="전적보정에서 라인 MMR 증감값입니다.",
        승변동="전적보정에서 통산 승수 증감값입니다.",
        패변동="전적보정에서 통산 패수 증감값입니다.",
        판수변동="전적보정에서 라인 판수 증감값입니다.",
        연승값="전적보정에서 연승값을 직접 지정합니다.",
    )
    async def recovery_manage_tools(
        interaction: discord.Interaction,
        작업: app_commands.Choice[str],
        유저: discord.Member = None,
        큐: str = None,
        라인: app_commands.Choice[str] = None,
        순번: app_commands.Range[int, 1, 50] = 1,
        챔피언: str = "",
        번호: app_commands.Range[int, 1, 100] = None,
        킬: app_commands.Range[int, 0, 99] = None,
        데스: app_commands.Range[int, 0, 99] = None,
        어시: app_commands.Range[int, 0, 99] = None,
        딜량: app_commands.Range[int, 0, 999999] = None,
        경기시간: str = "",
        스샷소환사명: str = "",
        적용: bool = False,
        승: app_commands.Range[int, 0, 999] = None,
        패: app_commands.Range[int, 0, 999] = None,
        판수도맞춤: bool = True,
        시작점수: app_commands.Range[int, 0, 4000] = None,
        mmr변동: int = 0,
        승변동: int = 0,
        패변동: int = 0,
        판수변동: int = 0,
        연승값: int = None,
    ):
        action = 작업.value
    
        if action == "undo_match":
            if 큐 is None:
                return await interaction.response.send_message("⚠️ 경기기록취소에는 큐를 선택해주세요.", ephemeral=True)
            return await undo_record(interaction, 큐)
    
        if action == "detail_edit":
            if 유저 is None:
                return await interaction.response.send_message("⚠️ 상세스탯수정에는 유저를 선택해주세요.", ephemeral=True)
            return await detail_stat_input(
                interaction,
                유저,
                순번=순번,
                챔피언=챔피언,
                킬=킬,
                데스=데스,
                어시=어시,
                딜량=딜량,
                경기시간=경기시간,
                스샷소환사명=스샷소환사명,
            )
    
        if action == "detail_delete":
            if 유저 is None or not 챔피언:
                return await interaction.response.send_message("⚠️ 상세데이터삭제에는 유저와 챔피언을 입력해주세요.", ephemeral=True)
            return await delete_champion_detail_data(interaction, 유저, 챔피언, 번호=번호)
    
        if action == "role_restore":
            return await restore_role_stats(interaction, 유저=유저)
    
        if action == "role_auto":
            if 유저 is None:
                return await interaction.response.send_message("⚠️ 라인전적자동보정에는 유저를 선택해주세요.", ephemeral=True)
            return await auto_correct_role_stats(interaction, 유저, 적용=적용)
    
        if action == "role_manual":
            if 유저 is None or 라인 is None or 승 is None or 패 is None:
                return await interaction.response.send_message("⚠️ 라인전적보정에는 유저, 라인, 승, 패를 모두 입력해주세요.", ephemeral=True)
            return await correct_role_stats(interaction, 유저, 라인, 승, 패, 판수도맞춤=판수도맞춤)
    
        if action == "role_estimate":
            if 유저 is None or 라인 is None or 시작점수 is None:
                return await interaction.response.send_message("⚠️ 라인전적추정보정에는 유저, 라인, 시작점수를 모두 입력해주세요.", ephemeral=True)
            return await estimate_correct_role_stats(interaction, 유저, 라인, 시작점수, 적용=적용)
    
        if action == "record_adjust":
            if 유저 is None or 라인 is None:
                return await interaction.response.send_message("⚠️ 전적보정에는 유저와 라인을 선택해주세요.", ephemeral=True)
            return await adjust_record(
                interaction,
                유저,
                라인,
                mmr변동=mmr변동,
                승변동=승변동,
                패변동=패변동,
                판수변동=판수변동,
                연승값=연승값,
            )
    
        await interaction.response.send_message("⚠️ 알 수 없는 복구관리 작업입니다.", ephemeral=True)
    
    async def restore_role_stats(interaction: discord.Interaction, 유저: discord.Member = None):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        if gid not in bot.user_data:
            return await interaction.response.send_message("⚠️ 복원할 서버 데이터가 없습니다.", ephemeral=True)
    
        targets = [(str(유저.id), bot.user_data[gid].get(str(유저.id)))] if 유저 else list(iter_user_records(bot.user_data[gid]))
        restored = []
        missing = []
        for uid, data in targets:
            if not isinstance(data, dict):
                continue
            rebuilt = restore_user_role_stats_from_history(gid, uid)
            if not rebuilt:
                missing.append(uid)
                continue
            total = sum(rebuilt[role]["win"] + rebuilt[role]["loss"] for role in ROLES)
            restored.append((uid, total, rebuilt))
    
        if restored:
            bot.save_lucid_data(gid)
    
        embed = discord.Embed(title="♻️ 라인별 전적 복원", color=0x2ecc71)
        if not restored:
            embed.description = "복원 가능한 경기 기록을 찾지 못했습니다."
            return await interaction.response.send_message(embed=embed, ephemeral=True)
    
        lines = []
        for uid, total, rebuilt in restored[:10]:
            name = get_member_display_name(interaction.guild, gid, uid)
            role_text = " / ".join(
                f"{role} {rebuilt[role]['win']}승{rebuilt[role]['loss']}패"
                for role in ROLES
                if rebuilt[role]["win"] + rebuilt[role]["loss"] > 0
            )
            lines.append(f"**{name}** · {total}전 · {role_text}")
        embed.description = "\n".join(lines)
        if len(restored) > 10:
            embed.set_footer(text=f"총 {len(restored)}명 복원 완료 · 상위 10명만 표시")
        elif missing:
            embed.set_footer(text=f"복원 기록 없음: {len(missing)}명")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def auto_correct_role_stats(interaction: discord.Interaction, 유저: discord.Member, 적용: bool = False):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        uid = str(유저.id)
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 해당 유저는 아직 등록되지 않은 소환사입니다.", ephemeral=True)
    
        await interaction.response.defer(ephemeral=True)
    
        user_info = ensure_user_format(bot.user_data[gid][uid])
        before_overall = (int(user_info.get("win", 0) or 0), int(user_info.get("loss", 0) or 0))
        before_stats = {
            role: dict(user_info.get("role_stats", {}).get(role, {"win": 0, "loss": 0}))
            for role in ROLES
        }
    
        inferred_roles = [infer_auto_role_record(gid, uid, user_info, role) for role in ROLES]
        total_wins = sum(item["wins"] for item in inferred_roles)
        total_losses = sum(item["losses"] for item in inferred_roles)
    
        if 적용:
            for item in inferred_roles:
                role = item["role"]
                role_streak = int(user_info["role_stats"][role].get("streak", 0) or 0)
                user_info["role_stats"][role] = {
                    "win": int(item["wins"]),
                    "loss": int(item["losses"]),
                    "streak": role_streak,
                }
                user_info["plays"][role] = int(item["games"])
            user_info["win"] = int(total_wins)
            user_info["loss"] = int(total_losses)
            bot.save_lucid_data(gid)
    
        embed = discord.Embed(
            title="🧮 라인별 전적 자동 보정",
            description=(
                f"{유저.mention} 님의 라인별 전적을 {'보정했습니다' if 적용 else '계산했습니다'}.\n"
                f"통산 승패: `{before_overall[0]}승 {before_overall[1]}패` → "
                f"`{total_wins}승 {total_losses}패`"
            ),
            color=0x2ecc71 if 적용 else 0xf1c40f
        )
    
        lines = []
        for item in inferred_roles:
            role = item["role"]
            old = before_stats.get(role, {"win": 0, "loss": 0})
            old_total = int(old.get("win", 0) or 0) + int(old.get("loss", 0) or 0)
            lines.append(
                f"**{role}** · {item['games']}판 · "
                f"`{old.get('win', 0)}승{old.get('loss', 0)}패/{old_total}판` → "
                f"`{item['wins']}승{item['losses']}패` · "
                f"시작 {item['start_mmr']} → 현재 {item['current_mmr']} · "
                f"기록 {item['history_games']}판 · {item['source']}"
            )
    
        embed.add_field(name="라인별 결과", value="\n".join(lines), inline=False)
        embed.set_footer(text="히스토리 이전 구간은 평가점수와 현재 MMR을 이용한 추정입니다. 적용=False로 미리보기만 할 수 있습니다.")
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def correct_role_stats(
        interaction: discord.Interaction,
        유저: discord.Member,
        라인: app_commands.Choice[str],
        승: app_commands.Range[int, 0, 999],
        패: app_commands.Range[int, 0, 999],
        판수도맞춤: bool = True,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        uid = str(유저.id)
        role_name = 라인.value
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 해당 유저는 아직 등록되지 않은 소환사입니다.", ephemeral=True)
    
        user_info = ensure_user_format(bot.user_data[gid][uid])
        before_stats = dict(user_info["role_stats"].get(role_name, {'win': 0, 'loss': 0}))
        before_plays = user_info["plays"].get(role_name, 0)
    
        user_info["role_stats"][role_name] = {
            'win': int(승),
            'loss': int(패),
            'streak': int(before_stats.get('streak', 0) or 0),
        }
        if 판수도맞춤:
            user_info["plays"][role_name] = int(승) + int(패)
    
        bot.save_lucid_data(gid)
    
        after_plays = user_info["plays"].get(role_name, 0)
        embed = discord.Embed(
            title="🛠️ 라인별 전적 보정 완료",
            description=f"{유저.mention} 님의 **{role_name}** 전적을 보정했습니다.",
            color=0x2ecc71
        )
        embed.add_field(
            name="변경 전",
            value=f"{before_stats.get('win', 0)}승 {before_stats.get('loss', 0)}패 · {before_plays}판",
            inline=True
        )
        embed.add_field(
            name="변경 후",
            value=f"{승}승 {패}패 · {after_plays}판",
            inline=True
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def estimate_correct_role_stats(
        interaction: discord.Interaction,
        유저: discord.Member,
        라인: app_commands.Choice[str],
        시작점수: app_commands.Range[int, 0, 4000],
        적용: bool = True,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        uid = str(유저.id)
        role_name = 라인.value
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 해당 유저는 아직 등록되지 않은 소환사입니다.", ephemeral=True)
    
        user_info = ensure_user_format(bot.user_data[gid][uid])
        games = int(user_info.get("plays", {}).get(role_name, 0) or 0)
        if games <= 0:
            return await interaction.response.send_message(f"⚠️ {유저.display_name} 님의 `{role_name}` 판수 기록이 없습니다.", ephemeral=True)
    
        current_mmr = int(user_info.get("mmr", {}).get(role_name, 0) or 0)
        inferred = infer_role_record_with_overall(gid, user_info, role_name, int(시작점수))
        wins = int(inferred["wins"])
        losses = int(inferred["losses"])
    
        before_stats = dict(user_info["role_stats"].get(role_name, {'win': 0, 'loss': 0}))
        before_plays = user_info["plays"].get(role_name, 0)
        if 적용:
            user_info["role_stats"][role_name] = {
                'win': wins,
                'loss': losses,
                'streak': int(before_stats.get('streak', 0) or 0),
            }
            user_info["plays"][role_name] = wins + losses
            bot.save_lucid_data(gid)
    
        embed = discord.Embed(
            title="🧮 라인별 전적 추정 보정",
            description=(
                f"{유저.mention} **{role_name}**\n"
                f"시작점수 `{시작점수}` → 현재 `{current_mmr}` / 저장 판수 `{games}판`\n"
                f"추정 방식: **{inferred['source']}**"
            ),
            color=0xf1c40f if not 적용 else 0x2ecc71
        )
        embed.add_field(
            name="기존 기록",
            value=f"{before_stats.get('win', 0)}승 {before_stats.get('loss', 0)}패 · {before_plays}판",
            inline=True
        )
        embed.add_field(
            name="추정 결과",
            value=f"**{wins}승 {losses}패** · {wins + losses}판",
            inline=True
        )
        other_details = inferred.get("other_details", [])
        if other_details:
            detail_lines = [
                f"{role} {wins_}승{losses_}패 ({source})"
                for role, _games, wins_, losses_, source in other_details
            ]
            embed.add_field(name="참고한 다른 라인", value="\n".join(detail_lines[:5]), inline=False)
        embed.set_footer(text="연승 보너스가 섞인 과거 데이터는 완전한 역산이 아니라 가장 합리적인 추정입니다.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def send_tier_evaluation_completion_dm(guild, user):
        gid = str(guild.id)
        uid = str(user.id)
        guild_name = discord.utils.escape_markdown(getattr(guild, "name", "서버") or "서버")
        message = (
            "✅ 티어 신청 평가 완료 안내\n\n"
            f"{guild_name} 서버에서 요청하신 티어 신청 평가가 완료되었습니다."
        )
        user_info = bot.user_data.get(gid, {}).get(uid)
        embed = build_my_info_embed(guild, gid, uid, user_info, user) if user_info else None
        await user.send(content=message, embed=embed, allowed_mentions=discord.AllowedMentions.none())
    
    def append_embed_footer(embed, text):
        current = getattr(embed.footer, "text", None) or ""
        embed.set_footer(text=f"{current}\n{text}" if current else text)
    
    async def evaluate_user(
        interaction: discord.Interaction,
        유저: discord.Member,
        라인: app_commands.Choice[str],
        티어: str,
        알림: app_commands.Choice[str] = None,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
    
        await interaction.response.defer(ephemeral=True)
    
        mmr_value, tier_input_label, tier_error = parse_mmr_evaluation_tier(티어)
        if tier_error:
            return await interaction.followup.send(f"⚠️ {tier_error}", ephemeral=True)
    
        gid = str(interaction.guild_id)
        uid = str(유저.id)
        role_name = 라인.value
        should_notify = bool(알림 and 알림.value == "send")
        operation_key = bot.begin_admin_operation(gid, f"mmr_eval:{uid}:{role_name}")
        if not operation_key:
            return await interaction.followup.send(f"⏳ {유저.display_name}님의 [{role_name}] MMR 평가가 이미 처리 중입니다.", ephemeral=True)
    
        try:
            if gid not in bot.user_data:
                bot.user_data[gid] = {}
            if uid not in bot.user_data[gid]:
                bot.user_data[gid][uid] = {
                    'mmr': {r:0 for r in ROLES},
                    'plays': {r:0 for r in ROLES},
                    'win': 0,
                    'loss': 0,
                    'streak': 0,
                    'lol_name': 유저.display_name,
                    'eval_scores': {r: [] for r in ROLES}
                }
    
            user_info = ensure_user_format(bot.user_data[gid][uid])
    
            if role_name == "노밴":
                before = get_noban_mmr(user_info)
                user_info['noban_mmr'] = int(mmr_value)
                bot.save_lucid_data(gid)
                await sync_registered_member_tier_role(interaction.guild, gid, uid)
    
                tier_name = get_tier_name(int(mmr_value))
                embed = discord.Embed(
                    title="🚫 노밴 MMR 배치 완료",
                    description=(
                        f"{유저.mention} 님의 노밴 모드 단일 MMR을 설정했습니다.\n"
                        "노밴 MMR은 노밴 모드에서만 사용되며, 노밴 MMR 참가자는 노밴 경기 결과에 따라 이 점수만 증감합니다."
                    ),
                    color=0x2b2d31,
                )
                embed.add_field(name="입력 티어", value=f"**{tier_input_label}**", inline=True)
                embed.add_field(name="변경", value=f"**{get_public_mmr_rank(before)} → {get_public_mmr_rank(mmr_value)}**", inline=True)
                embed.add_field(name="노밴 등급", value=f"**{format_public_mmr(mmr_value, interaction.guild, gid)}**", inline=False)
                if should_notify:
                    try:
                        await send_tier_evaluation_completion_dm(interaction.guild, 유저)
                        append_embed_footer(embed, "유저에게 티어 신청 평가 완료 DM을 보냈습니다.")
                    except discord.Forbidden:
                        append_embed_footer(embed, "유저 DM이 닫혀 있어 티어 신청 평가 완료 알림을 보내지 못했습니다.")
                    except discord.HTTPException as exc:
                        append_embed_footer(embed, f"티어 신청 평가 완료 DM 전송 실패: {str(exc)[:180]}")
                return await interaction.followup.send(embed=embed, ephemeral=True)
    
            if is_role_mmr_assigned(user_info, role_name):
                return await interaction.followup.send(
                    f"⚠️ **{유저.display_name}** 님의 [{role_name}] MMR은 이미 배치가 끝나서 수정할 수 없습니다.",
                    ephemeral=True
                )
    
            user_info['eval_scores'][role_name].append(int(mmr_value))
            line_avg_mmr = sum(user_info['eval_scores'][role_name]) // len(user_info['eval_scores'][role_name])
            user_info['mmr'][role_name] = line_avg_mmr
    
            bot.save_lucid_data(gid)
            await sync_registered_member_tier_role(interaction.guild, gid, uid)
    
            total_avg_mmr = get_avg_mmr(user_info['mmr'])
            tier_name = get_tier_name(total_avg_mmr)
            eval_count = len(user_info['eval_scores'][role_name])
    
            role_marker = get_role_display_marker(role_name, interaction.guild)
            embed = discord.Embed(title=f"📊 {role_marker} 배치 기록", color=0x3498db)
            content = None
    
            if eval_count >= MMR_EVAL_REQUIRED_COUNT:
                content = f"🎊 {유저.mention} 님의 {role_marker} 라인 배치가 완료되었습니다."
                embed.description = f"{role_marker} 포지션 확정 레이팅: **{format_public_mmr(line_avg_mmr, interaction.guild, gid)}**"
            else:
                embed.description = f"{유저.mention} 님의 {role_marker} 라인 {eval_count}차 배치 기록입니다."
                embed.set_footer(text=f"남은 배치 횟수: {MMR_EVAL_REQUIRED_COUNT - eval_count}회")
    
            embed.add_field(name="입력 티어", value=f"⭐ {tier_input_label}", inline=True)
            embed.add_field(name="배치 환산 점수", value=f"**{int(mmr_value)}점**", inline=True)
            embed.add_field(name="라인 MMR", value=f"{role_marker} {format_public_mmr(line_avg_mmr, interaction.guild, gid)}", inline=True)
            embed.add_field(name="종합 티어", value=f"{format_public_mmr(total_avg_mmr, interaction.guild, gid)}", inline=False)
    
            if should_notify:
                try:
                    await send_tier_evaluation_completion_dm(interaction.guild, 유저)
                    append_embed_footer(embed, "유저에게 티어 신청 평가 완료 DM을 보냈습니다.")
                except discord.Forbidden:
                    append_embed_footer(embed, "유저 DM이 닫혀 있어 티어 신청 평가 완료 알림을 보내지 못했습니다.")
                except discord.HTTPException as exc:
                    append_embed_footer(embed, f"티어 신청 평가 완료 DM 전송 실패: {str(exc)[:180]}")
    
            await interaction.followup.send(content=content, embed=embed, ephemeral=True)
        finally:
            bot.finish_admin_operation(operation_key)
    
    async def adjust_record(
        interaction: discord.Interaction,
        유저: discord.Member,
        라인: app_commands.Choice[str],
        mmr변동: int = 0,
        승변동: int = 0,
        패변동: int = 0,
        판수변동: int = 0,
        연승값: int = None
    ):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("🚫 디스코드 서버 관리자 자격(Administrator)이 요구됩니다.", ephemeral=True)
    
        await interaction.response.defer(ephemeral=True)
    
        gid = str(interaction.guild_id)
        uid = str(유저.id)
        role_name = 라인.value
    
        bot.user_data.setdefault(gid, {})
        if uid not in bot.user_data[gid]:
            bot.user_data[gid][uid] = {
                'mmr': {r: 0 for r in ROLES},
                'plays': {r: 0 for r in ROLES},
                'eval_scores': {r: [] for r in ROLES},
                'win': 0,
                'loss': 0,
                'streak': 0,
                'lol_name': 유저.display_name
            }
    
        user_info = ensure_user_format(bot.user_data[gid][uid])
        before = {
            'mmr': user_info['mmr'].get(role_name, 0),
            'plays': user_info['plays'].get(role_name, 0),
            'win': user_info.get('win', 0),
            'loss': user_info.get('loss', 0),
            'streak': user_info.get('streak', 0)
        }
    
        user_info['mmr'][role_name] = max(0, before['mmr'] + mmr변동)
        user_info['plays'][role_name] = max(0, before['plays'] + 판수변동)
        user_info['win'] = max(0, before['win'] + 승변동)
        user_info['loss'] = max(0, before['loss'] + 패변동)
        if 연승값 is not None:
            user_info['streak'] = 연승값
            user_info['role_stats'][role_name]['streak'] = 연승값
    
        bot.user_data[gid][uid] = user_info
        bot.save_lucid_data(gid)
        await sync_registered_member_tier_role(interaction.guild, gid, uid)
    
        after = {
            'mmr': user_info['mmr'].get(role_name, 0),
            'plays': user_info['plays'].get(role_name, 0),
            'win': user_info.get('win', 0),
            'loss': user_info.get('loss', 0),
            'streak': user_info.get('streak', 0)
        }
    
        embed = discord.Embed(
            title="🛠️ 전적 보정 완료",
            description=f"{유저.mention} 소환사의 **[{role_name}]** 기록을 수동 보정했습니다.",
            color=0xe67e22
        )
        embed.add_field(
            name="라인 MMR / 판수",
            value=f"MMR: **{before['mmr']} → {after['mmr']}**\n판수: **{before['plays']} → {after['plays']}**",
            inline=True
        )
        embed.add_field(
            name="통산 승패 / 흐름",
            value=f"승: **{before['win']} → {after['win']}**\n패: **{before['loss']} → {after['loss']}**\n연승값: **{before['streak']} → {after['streak']}**",
            inline=True
        )
        embed.set_footer(text="복구용 명령어입니다. 필요한 만큼만 신중하게 사용해주세요.")
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def sync_tier_roles_command(interaction: discord.Interaction, 유저: discord.Member = None):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("🚫 디스코드 서버 관리자 자격(Administrator)이 요구됩니다.", ephemeral=True)
    
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        guild_data = bot.user_data.get(gid, {})
        icon_updates, icon_failures = await apply_auto_tier_role_icons(
            interaction.guild,
            reason=f"{interaction.user.display_name} 관리자 티어 역할 아이콘 동기화",
        )
    
        targets = [(str(유저.id), guild_data.get(str(유저.id)))] if 유저 else list(iter_user_records(guild_data))
        if 유저 and not isinstance(targets[0][1], dict):
            result = await remove_member_auto_tier_roles(
                interaction.guild,
                유저,
                reason=f"{interaction.user.display_name} 관리자 티어 역할 동기화",
            )
            if result.get("status") == "changed":
                return await interaction.followup.send(
                    f"✅ 등록/배치 데이터가 없는 유저라 자동 티어 역할을 제거했습니다: {유저.mention}",
                    ephemeral=True,
                )
            return await interaction.followup.send("⚠️ 해당 유저는 등록된 소환사가 아니며 제거할 자동 티어 역할도 없습니다.", ephemeral=True)
    
        extra_unregistered_members = []
        if not 유저:
            registered_uids = {str(uid) for uid, _data in targets}
            seen_member_ids = set()
            for role in get_auto_tier_roles(interaction.guild).values():
                for member in getattr(role, "members", []) or []:
                    uid = str(getattr(member, "id", ""))
                    if not uid or uid in registered_uids or uid in seen_member_ids:
                        continue
                    seen_member_ids.add(uid)
                    extra_unregistered_members.append(member)
    
        total = len(targets) + len(extra_unregistered_members)
        if total <= 0:
            return await interaction.followup.send("⚠️ 등록된 소환사 데이터나 정리할 티어 역할 보유자가 없습니다.", ephemeral=True)
        history_peak_map = build_history_peak_mmr_map(gid)
        progress_message = await interaction.followup.send(
            (
                "⏳ **티어 역할 동기화 시작**\n"
                f"대상 **{total}명** 확인 중...\n"
                "디스코드 역할 변경 제한 때문에 잠시 걸릴 수 있습니다."
            ),
            ephemeral=True,
            wait=True,
        )
    
        counts = defaultdict(int)
        changed_lines = []
        processed = 0
        for uid, user_info in targets:
            processed += 1
            result = await sync_registered_member_tier_role(
                interaction.guild,
                gid,
                uid,
                reason=f"{interaction.user.display_name} 관리자 티어 역할 동기화",
                history_peak=history_peak_map.get(str(uid)),
            )
            status = result.get("status", "unknown")
            counts[status] += 1
            if status == "changed":
                member_name = get_member_display_name(interaction.guild, gid, uid)
                score = int(result.get("score", 0) or 0)
                score_text = f" · {score}점" if score > 0 else ""
                changed_lines.append(f"• {member_name} → {result.get('role')}{score_text}")
            if processed == total or processed % 10 == 0:
                progress_text = (
                    "⏳ **티어 역할 동기화 중**\n"
                    f"진행률 **{processed}/{total}명**\n"
                    f"변경 **{counts['changed']}명** · 유지 **{counts['unchanged']}명** · "
                    f"역할 없음 **{counts['missing_role']}명** · 권한 부족 **{counts['unmanageable'] + counts['forbidden']}명** · "
                    f"건너뜀 **{counts['skipped']}명**"
                )
                try:
                    await progress_message.edit(content=progress_text)
                except discord.HTTPException:
                    pass
    
        for member in extra_unregistered_members:
            processed += 1
            result = await remove_member_auto_tier_roles(
                interaction.guild,
                member,
                reason=f"{interaction.user.display_name} 관리자 티어 역할 동기화",
            )
            status = result.get("status", "unknown")
            counts[status] += 1
            if status == "changed":
                member_name = discord.utils.escape_markdown(getattr(member, "display_name", str(member.id)))
                changed_lines.append(f"• {member_name} → 역할 제거")
            if processed == total or processed % 10 == 0:
                progress_text = (
                    "⏳ **티어 역할 동기화 중**\n"
                    f"진행률 **{processed}/{total}명**\n"
                    f"변경 **{counts['changed']}명** · 유지 **{counts['unchanged']}명** · "
                    f"역할 없음 **{counts['missing_role']}명** · 권한 부족 **{counts['unmanageable'] + counts['forbidden']}명** · "
                    f"건너뜀 **{counts['skipped']}명**"
                )
                try:
                    await progress_message.edit(content=progress_text)
                except discord.HTTPException:
                    pass
    
        summary = (
            f"변경 **{counts['changed']}명** · 유지 **{counts['unchanged']}명** · "
            f"역할 없음 **{counts['missing_role']}명** · 권한 부족 **{counts['unmanageable'] + counts['forbidden']}명** · "
            f"건너뜀 **{counts['skipped']}명**"
        )
        if extra_unregistered_members:
            summary += f"\n미등록 티어 역할 보유자 정리 대상 **{len(extra_unregistered_members)}명** 포함"
        summary += f"\n티어 역할 아이콘 적용 **{len(icon_updates)}개** · 실패 **{len(icon_failures)}개**"
        embed = discord.Embed(
            title="🏷️ 티어 역할 동기화 완료",
            description=summary,
            color=0x2ecc71,
        )
        if changed_lines:
            embed.add_field(name="변경된 유저", value="\n".join(changed_lines[:20]), inline=False)
        if icon_failures:
            embed.add_field(name="아이콘 적용 실패 일부", value=", ".join(icon_failures[:8])[:1000], inline=False)
        embed.set_footer(text="역대 최고 MMR 기준입니다. 배치 기록이 없는 유저는 자동 티어 역할을 제거합니다.")
        bot.save_lucid_data(gid)
        await progress_message.edit(content=None, embed=embed)
    
    
    async def reset_user(interaction: discord.Interaction, 유저: discord.Member, 라인: app_commands.Choice[str] = None):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("🚫 디스코드 서버 관리자 자격(Administrator)이 요구됩니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        uid = str(유저.id)
        operation_key = bot.begin_admin_operation(gid, f"mmr_reset:{uid}")
        if not operation_key:
            return await reject_duplicate_admin_operation(interaction, f"{유저.display_name} MMR 초기화")
    
        try:
            if gid in bot.user_data and uid in bot.user_data[gid]:
                current_data = ensure_user_format(bot.user_data[gid][uid])
    
                if 라인:
                    role_name = 라인.value
                    old_mmr = current_data['mmr'].get(role_name, 0)
                    old_plays = current_data['plays'].get(role_name, 0)
                    current_data['mmr'][role_name] = 0
                    current_data['plays'][role_name] = 0
                    current_data['eval_scores'][role_name] = []
                    current_data['role_stats'][role_name]['streak'] = 0
                    bot.user_data[gid][uid] = current_data
                    bot.save_lucid_data(gid)
                    await sync_registered_member_tier_role(interaction.guild, gid, uid)
                    return await interaction.response.send_message(
                        f"🧹 라인 초기화 완료: {유저.display_name} 님의 **[{role_name}]** 레이팅을 0점으로 초기화했습니다. "
                        f"(기존 {old_mmr}점 / {old_plays}판, 통산 승패는 유지)",
                        ephemeral=True,
                    )
    
                bot.user_data[gid][uid] = {
                    'lol_name': current_data.get('lol_name', 유저.display_name),
                    'mmr': {r:0 for r in ROLES},
                    'plays': current_data.get('plays'),
                    'eval_scores': {r: [] for r in ROLES},
                    'win': current_data.get('win', 0),
                    'loss': current_data.get('loss', 0),
                    'streak': 0,
                    'event_stats': current_data.get('event_stats', {})
                }
                bot.save_lucid_data(gid)
                await sync_registered_member_tier_role(interaction.guild, gid, uid)
                await interaction.response.send_message(f"🧹 초기화 완료: {유저.display_name} 님의 승패는 유지하고, 모든 라인 MMR과 연승 기록을 0으로 돌렸습니다.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ 해당 유저 데이터를 찾지 못했습니다.", ephemeral=True)
        finally:
            bot.finish_admin_operation(operation_key)


    exported = locals().copy()
    exported.pop("runtime", None)
    return exported
