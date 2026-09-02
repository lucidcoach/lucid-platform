"""ROFL uploads, detailed stats, match analysis, and replay reports."""

import asyncio
import copy
from dataclasses import dataclass, field

import discord
from discord import app_commands
from lucidgame_replay_detail import DetailSaveDependencies, save_detail_entries as save_replay_detail_entries


def require_runtime_callables(values, names):
    """Fail startup with one actionable error when replay dependencies are missing."""
    missing = [name for name in names if not callable((values or {}).get(name))]
    if missing:
        raise RuntimeError("리플레이 런타임 callable 누락: " + ", ".join(missing))
    return values


@dataclass
class MatchAnalysisContext:
    """Stable input/output bundle shared by match-analysis role builders.

    The replay decoder still owns the raw dictionaries.  This small container
    only gives the role builders one explicit object to receive, so a new
    local alias cannot accidentally leak between role paths.
    """

    guild: object = None
    gid: str = ""
    player_name: str = ""
    role: str = ""
    champion: str = ""
    opponent_champion: str = ""
    participant_id: int = 0
    opponent_id: int = 0
    target_team: str = ""
    enemy_team: str = ""
    rofl_rows: list = field(default_factory=list)
    checkpoint_analysis: dict = field(default_factory=dict)
    player_series: list = field(default_factory=list)
    opponent_final_row: dict = None
    kill_events: list = field(default_factory=list)
    objective_events: list = field(default_factory=list)
    tower_events: list = field(default_factory=list)
    quest_events: list = field(default_factory=list)
    patch_label: str = "16.16"
    patch_display_label: str = "26.16"
    pages: list = field(default_factory=list)
    page_labels: tuple = ()
    values: dict = field(default_factory=dict)


def make_match_analysis_context(**values):
    """Create the shared analysis context without touching runtime state."""

    return MatchAnalysisContext(**values)


def _build_1617_safe_analysis_context(
    *, participant, participants, rofl_rows, checkpoint_analysis,
    resolved_riot_id="", normalize_rofl_match_name=str, target_team=None,
):
    """Render exact-build 16.17 facts without unverified state estimates."""
    pid = int((participant or {}).get("participant_id", 0) or 0)
    team = str(target_team or (participant or {}).get("team") or "")
    player_name = (participant or {}).get("riot_id") or resolved_riot_id or ("블루팀" if team == "blue" else "레드팀")
    role = str((participant or {}).get("role") or ("팀" if target_team else "미지정"))
    pages = [discord.Embed(title=f"{player_name} 리포트 - 26.17 패치", color=0x5865F2) for _ in range(4)]
    identity = {int(row.get("participant_id", 0) or 0): row for row in participants}
    opponent = next(
        (
            row for row in participants
            if str(row.get("team") or "") != team and str(row.get("role") or "") == role
        ),
        {},
    )
    matchup = f"⚔️ **{role} · {(participant or {}).get('champion', '?')} vs {opponent.get('champion', '?')}**"
    for page in pages:
        page.description = matchup

    def belongs(target_pid):
        return bool(target_pid) and (
            int(target_pid) == pid if pid
            else str((identity.get(int(target_pid)) or {}).get("team") or "") == team
        )

    if pid and 0 < pid <= len(rofl_rows):
        final_rows = [rofl_rows[pid - 1]]
    else:
        final_rows = [row for index, row in enumerate(rofl_rows, 1) if belongs(index)]
    kills = list(checkpoint_analysis.get("kills") or [])
    own_kills = [event for event in kills if belongs(event.get("killer_id"))]
    own_deaths = [event for event in kills if belongs(event.get("victim_id"))]
    own_assists = [event for event in kills if pid and pid in [int(x) for x in event.get("assist_ids", [])]]

    final_k = sum(int(row.get("kills", 0) or 0) for row in final_rows)
    final_d = sum(int(row.get("deaths", 0) or 0) for row in final_rows)
    final_a = sum(int(row.get("assists", 0) or 0) for row in final_rows)
    role_field = {
        "탑": "⚔️ 15분 전 킬 관여", "정글": "🗺️ 15분 전 개입 타임라인",
        "미드": "🔥 킬 영향력 타임라인", "원딜": "🔥 경기 전체 딜링",
        "서폿": "🤝 15분 전 킬 관여",
    }.get(role, "📊 최종 KDA")
    pages[0].add_field(name=role_field, value=f"최종 KDA **{final_k} / {final_d} / {final_a}**", inline=False)
    pages[0].add_field(name="✅ 검증 상태", value="최종 전적과 replay KDA 이벤트가 서로 일치합니다.", inline=False)

    involved = [
        event for event in kills
        if belongs(event.get("killer_id")) or belongs(event.get("victim_id"))
        or (pid and pid in [int(x) for x in event.get("assist_ids", [])])
    ]
    event_lines = []
    for event in involved[-12:]:
        seconds = int(event.get("time_ms", 0) or 0) // 1000
        result = "킬" if belongs(event.get("killer_id")) else "데스" if belongs(event.get("victim_id")) else "어시스트"
        event_lines.append(f"`{seconds // 60}:{seconds % 60:02d}` {result}")
    pages[1].add_field(
        name=f"⚔️ 킬 {len(own_kills)} · 데스 {len(own_deaths)}" + (f" · 어시 {len(own_assists)}" if pid else ""),
        value="\n".join(event_lines) if event_lines else "표시할 교전 이벤트가 없습니다.", inline=False,
    )

    objectives = [
        event for event in (checkpoint_analysis.get("objectives") or checkpoint_analysis.get("objective_events") or [])
        if str(event.get("team") or "") == team
    ]
    towers = [event for event in checkpoint_analysis.get("towers", []) if str(event.get("team") or "") == team]
    objective_names = {"DRAGON": "드래곤", "BARON": "바론", "RIFT_HERALD": "전령"}
    objective_lines = []
    for event in objectives[-8:]:
        seconds = int(event.get("time_ms", 0) or 0) // 1000
        nearby = [item for item in kills if abs(int(item.get("time_ms", 0) or 0) - int(event.get("time_ms", 0) or 0)) <= 45_000]
        participation = sum(
            1 for item in nearby
            if int(item.get("killer_id", 0) or 0) == pid or pid in [int(x) for x in item.get("assist_ids", [])]
        ) if pid else 0
        name = objective_names.get(event.get("objective"), "오브젝트")
        objective_lines.append(
            f"🟢 **{seconds // 60}분 {seconds % 60:02d}초 · {name} 획득**\n"
            f"└ 주변 교전 {len(nearby)}건 · 본인 참여 {participation}건"
        )
    pages[2].add_field(
        name="🐉 오브젝트 분석",
        value="\n".join(objective_lines) if objective_lines else "확인된 오브젝트 이벤트가 없습니다.", inline=False,
    )

    pages[3].add_field(
        name="🔒 제외된 데이터",
        value="Gold/XP/전체 CS 분 단위 값은 아직 독립 검증을 통과하지 않아 표시하지 않습니다.", inline=False,
    )
    warnings = list(checkpoint_analysis.get("decoder_warnings") or [])
    if warnings:
        pages[3].add_field(name="ℹ️ 일부 이벤트 안내", value="\n".join(warnings[:3]), inline=False)

    labels = ("📊 최종 기록", "⚔️ 교전", "🐉 오브젝트", "🔒 분석 범위")
    for index, page in enumerate(pages):
        page.set_footer(text=f"{index + 1} / 4 · {labels[index]}")
    return MatchAnalysisContext(
        player_name=str(player_name), role=role, participant_id=pid,
        target_team=team, enemy_team="red" if team == "blue" else "blue",
        rofl_rows=rofl_rows, checkpoint_analysis=checkpoint_analysis,
        kill_events=kills, objective_events=objectives, tower_events=towers,
        patch_label="16.17", patch_display_label="26.17", pages=pages, page_labels=labels,
    )


def resolve_analysis_matchup(
    participant=None,
    participants=None,
    rofl_rows=None,
    player_series=None,
    *,
    opponent_id=None,
    opponent_identity=None,
    opponent_final_row=None,
):
    """Resolve one participant's same-role opponent without self-references."""

    participant = participant or {}
    participants = participants or []
    rofl_rows = rofl_rows or []
    participant_id = int(participant.get("participant_id", 0) or 0)
    target_team = str(participant.get("team") or "")
    enemy_team = "red" if target_team == "blue" else "blue"

    if opponent_id is None:
        for frame in player_series or []:
            row = frame.get("row") or {}
            if int(row.get("participant_id", 0) or 0) == participant_id and row.get("opponent_id"):
                opponent_id = int(row["opponent_id"])
                break
    if opponent_id is None:
        role_aliases = {
            "TOP": "TOP", "탑": "TOP",
            "JUNGLE": "JUNGLE", "정글": "JUNGLE",
            "MIDDLE": "MIDDLE", "MID": "MIDDLE", "미드": "MIDDLE",
            "BOTTOM": "BOTTOM", "BOT": "BOTTOM", "원딜": "BOTTOM",
            "UTILITY": "UTILITY", "SUPPORT": "UTILITY", "서폿": "UTILITY",
        }
        wanted_role = role_aliases.get(str(participant.get("role") or "").strip().upper())
        if wanted_role:
            opponent = next(
                (
                    row for row in participants
                    if str(row.get("team") or "") == enemy_team
                    and role_aliases.get(
                        str(row.get("role") or row.get("position") or row.get("team_position") or "").strip().upper()
                    ) == wanted_role
                ),
                None,
            )
            opponent_id = int((opponent or {}).get("participant_id", 0) or 0) or None
    opponent_id = int(opponent_id or 0) or None

    if opponent_identity is None and opponent_id:
        opponent_identity = next(
            (
                row for row in participants
                if int(row.get("participant_id", 0) or 0) == opponent_id
            ),
            None,
        )
    opponent_identity = opponent_identity or {}

    def _champion(row):
        return str((row or {}).get("champion") or "").strip()

    opponent_champion = _champion(opponent_identity) or "상대 챔피언"
    if opponent_final_row is None and opponent_identity:
        target_name = str(opponent_identity.get("riot_id") or "").strip().lower().replace(" ", "")
        opponent_final_row = next(
            (
                row for row in rofl_rows
                if str(row.get("summoner_name") or "").strip().lower().replace(" ", "") == target_name
            ),
            None,
        )

    return {
        "participant_id": participant_id,
        "role": str(participant.get("role") or "미지정"),
        "champion": _champion(participant),
        "target_team": target_team,
        "enemy_team": enemy_team,
        "opponent_id": opponent_id,
        "opponent_identity": opponent_identity or None,
        "opponent_champion_name": opponent_champion,
        "opponent_final_row": opponent_final_row,
    }


def _placeholder_analysis_pages(ctx, role):
    """Return four safe embeds for isolated builder/smoke calls."""

    labels = tuple(ctx.page_labels or ("🌱 성장", "🧭 운영", "⚔️ 교전", "📋 총정리"))
    champion = ctx.champion or "챔피언"
    opponent = ctx.opponent_champion or "상대 챔피언"
    title = f"{ctx.player_name or '테스트유저'} 리포트 - {ctx.patch_display_label or '26.16'} 패치"
    pages = [
        discord.Embed(
            title=title,
            description=f"⚔️ **{role} · {champion} vs {opponent}**",
            color=0x5865F2,
        )
        for _ in range(4)
    ]
    for index, page in enumerate(pages):
        page.set_footer(text=f"{index + 1} / 4 · {labels[index] if index < len(labels) else '경기분석'}")
    return pages


def build_top_analysis_pages(ctx):
    values = ctx.values or {}
    if not values or any(key not in values for key in ["_team_gold_gap_from_series","champion","format_game_time","gold_gap_delta_text","gold_gap_state","opponent_champion_name","opponent_id","participant_id","patch_label","quest_time_ms","series_after_ms","series_before_ms","target_team","top_enemy_outer_tower","top_fight_line","top_lane_2v2_fights","top_post_tower_objective_lines","top_prequest_swings","top_quest_compare_text","top_side_operation_text","top_swing_text"]):
        return _placeholder_analysis_pages(ctx, "탑")
    if values.get("_smoke"):
        return _placeholder_analysis_pages(ctx, "탑")
    _team_gold_gap_from_series = values["_team_gold_gap_from_series"]
    champion = values["champion"]
    format_game_time = values["format_game_time"]
    gold_gap_delta_text = values["gold_gap_delta_text"]
    gold_gap_state = values["gold_gap_state"]
    opponent_champion_name = values["opponent_champion_name"]
    opponent_id = values["opponent_id"]
    participant_id = values["participant_id"]
    patch_label = values["patch_label"]
    quest_time_ms = values["quest_time_ms"]
    series_after_ms = values["series_after_ms"]
    series_before_ms = values["series_before_ms"]
    target_team = values["target_team"]
    top_enemy_outer_tower = values["top_enemy_outer_tower"]
    top_fight_line = values["top_fight_line"]
    top_lane_2v2_fights = values["top_lane_2v2_fights"]
    top_post_tower_objective_lines = values["top_post_tower_objective_lines"]
    top_prequest_swings = values["top_prequest_swings"]
    top_quest_compare_text = values["top_quest_compare_text"]
    top_side_operation_text = values["top_side_operation_text"]
    top_swing_text = values["top_swing_text"]
    early_embed, operation_embed, combat_embed, weakness_embed = ctx.pages
    top_tower = top_enemy_outer_tower()
    opponent_champion = opponent_champion_name
    top_header = f"⚔️ **탑 · {champion} vs {opponent_champion}**"

    early_embed.clear_fields()
    early_embed.title = f"🌱 탑 라인전 - {patch_label}"
    early_embed.description = top_header
    early_embed.add_field(name="🎯 퀘스트 완료", value=top_quest_compare_text(), inline=False)
    if top_tower:
        tower_ms = int(top_tower.get("time_ms", 0) or 0)
        early_embed.add_field(name="🏰 1차 타워", value=f"**{format_game_time(tower_ms)} · 탑 1차 포탑 파괴**", inline=False)
        before, after = series_before_ms(tower_ms), series_after_ms(tower_ms + 5 * 60_000)
        if before and after:
            early_embed.add_field(
                name="❄️ 1차 포탑 이후 5분 스노우볼",
                value=(
                    f"**{format_game_time(tower_ms)} ~ {format_game_time(tower_ms + 5 * 60_000)}**\n"
                    f"└ 팀 골드 격차 `{gold_gap_state(_team_gold_gap_from_series(before, target_team))}` "
                    f"→ `{gold_gap_state(_team_gold_gap_from_series(after, target_team))}`"
                ), inline=False,
            )
    swings = top_prequest_swings()
    if swings:
        worst, best = min(swings, key=lambda x: x["gap_change"]), max(swings, key=lambda x: x["gap_change"])
        early_embed.add_field(name="📉 상대에게 가장 많이 따라잡힌 구간", value=top_swing_text(worst), inline=False)
        if best["gap_change"] != worst["gap_change"]:
            early_embed.add_field(name="📈 상대와 격차를 가장 크게 벌린 구간", value=top_swing_text(best), inline=False)
    early_embed.set_footer(text="1 / 4 · 라인전")

    operation_embed.clear_fields()
    operation_embed.title = f"🧭 탑 사이드 운영 - {patch_label}"
    operation_embed.description = top_header + "\n상대 탑 1차 포탑 파괴 이후만 분석"
    operation_embed.add_field(name="📈 1차 포탑 이후 5분 운영", value=top_side_operation_text(top_tower), inline=False)
    operation_embed.set_footer(text="2 / 4 · 사이드 운영")

    combat_embed.clear_fields()
    combat_embed.title = f"⚔️ 탑 교전 분석 - {patch_label}"
    combat_embed.description = top_header
    lane_fights = top_lane_2v2_fights(top_tower)
    combat_embed.add_field(
        name="🛡️ 1차 포탑 전후 · 탑 2:2+ 교전",
        value="\n\n".join(top_fight_line(f) for f in lane_fights[:4]) if lane_fights else "양 팀 2명 이상 + 양쪽 탑이 함께 연결된 교전이 없습니다.",
        inline=False,
    )
    objective_lines = top_post_tower_objective_lines(top_tower, limit=4)
    combat_embed.add_field(
        name="🐉 1차 포탑 이후 오브젝트 교전",
        value="\n\n".join(objective_lines) if objective_lines else "분석 가능한 오브젝트 교전이 없습니다.",
        inline=False,
    )
    combat_embed.set_footer(text="3 / 4 · 교전")

    weakness_embed.clear_fields()
    weakness_embed.title = f"📋 탑 총정리 - {patch_label}"
    weakness_embed.description = top_header
    top_good, top_fix = [], []

    my_q, opp_q = quest_time_ms(participant_id), (quest_time_ms(opponent_id) if opponent_id else 0)
    if my_q and opp_q:
        diff = int(round((opp_q - my_q) / 1000.0))
        if diff > 0:
            top_good.append(f"✅ **라인전 퀘스트 우위** · 상대보다 `{diff}초` 빠르게 완료해 초반 성장 템포가 좋았습니다.")
        elif diff < 0:
            top_fix.append(f"⚠️ **퀘스트 완료가 `{abs(diff)}초` 늦었습니다.** 퀘스트 전 CS/레벨 손실 구간을 우선 확인할 필요가 있습니다.")

    if swings:
        worst, best = min(swings, key=lambda x: x["gap_change"]), max(swings, key=lambda x: x["gap_change"])
        if best["gap_change"] >= 300:
            top_good.append(f"📈 **{best['from']}~{best['to']}분 성장 우위** · 상대 탑과 골드 격차를 `{best['gap_change']:+,}G` 더 유리하게 만들었습니다.")
        if worst["gap_change"] <= -300:
            top_fix.append(
                f"📉 **{worst['from']}~{worst['to']}분 상대 성장 허용** · 내 획득 `{worst['my_gain']:,}G`보다 상대가 `{worst['opp_gain']:,}G`를 벌며 "
                f"라인 골드 격차가 `{worst['gap_change']:+,}G` 악화됐습니다. 이 구간의 CS 손실·귀환 타이밍·웨이브 처리를 먼저 복기하는 것이 좋습니다."
            )

    if top_tower:
        tower_ms = int(top_tower.get("time_ms", 0) or 0)
        before, after = series_before_ms(tower_ms), series_after_ms(tower_ms + 5 * 60_000)
        if before and after and before.get("opp") and after.get("opp"):
            br, bo, ar, ao = before["row"], before["opp"], after["row"], after["opp"]
            rel = (
                (int(ar.get("total_gold", 0) or 0) - int(br.get("total_gold", 0) or 0))
                - (int(ao.get("total_gold", 0) or 0) - int(bo.get("total_gold", 0) or 0))
            )
            team_before, team_after = _team_gold_gap_from_series(before, target_team), _team_gold_gap_from_series(after, target_team)
            if rel >= 300:
                top_good.append(f"🧭 **1차 포탑 이후 사이드 성장** · 5분 동안 상대 탑보다 `{rel:,}G` 더 벌었습니다.")
            elif rel <= -300:
                top_fix.append(
                    f"🧭 **1차 포탑 이후 리드 전환 부족** · 포탑을 먼저 밀었지만 이후 5분 동안 상대 탑보다 `{abs(rel):,}G` 덜 벌었습니다. "
                    f"사이드 웨이브·타워 압박·합류 타이밍 중 어디에서 리드가 멈췄는지 확인할 필요가 있습니다."
                )
            if team_after - team_before <= -1000:
                top_fix.append(
                    f"🌍 **개인 운영과 팀 흐름 분리 필요** · 같은 5분 동안 팀 골드 격차가 {gold_gap_delta_text(team_before, team_after)}로 악화됐습니다. "
                    f"사이드에서 얻은 이득이 팀 오브젝트/교전으로 연결됐는지 복기하는 것이 좋습니다."
                )
            elif team_after - team_before >= 1000:
                top_good.append(
                    f"❄️ **스노우볼 연결** · 1차 포탑 이후 5분 동안 팀 골드 격차도 {gold_gap_delta_text(team_before, team_after)}로 좋아졌습니다."
                )

    shares = [float(f["target_damage_share"]) for f in lane_fights if f.get("target_damage_share") is not None]
    if shares:
        avg_share = sum(shares) / len(shares)
        if avg_share >= 25:
            top_good.append(f"⚔️ **탑 2:2+ 교전 딜 기여** · 분석 가능한 교전에서 평균 팀 딜 비중 `{avg_share:.0f}%`.")
        elif avg_share < 15:
            top_fix.append(
                f"⚔️ **탑 2:2+ 교전 딜 기여가 낮았습니다.** 분석 가능한 교전 평균 팀 딜 비중이 `{avg_share:.0f}%`라서 "
                f"진입 타이밍과 딜 가능한 시간을 복기할 가치가 있습니다."
            )

    if not top_good:
        top_good.append("뚜렷한 강점은 추가 표본과 함께 확인하는 것이 좋습니다.")
    if not top_fix:
        top_fix.append("큰 손실로 분류되는 구간이 적습니다. 세부 웨이브/교전 복기는 장면 단위로 확인하면 좋습니다.")
    weakness_embed.add_field(name="✨ 좋은점", value="\n\n".join(top_good[:4]), inline=False)
    weakness_embed.add_field(name="🛠️ 보완점", value="\n\n".join(top_fix[:4]), inline=False)
    weakness_embed.set_footer(text="4 / 4 · 총정리")

    return [early_embed, operation_embed, combat_embed, weakness_embed]

def build_jungle_analysis_pages(ctx):
    values = ctx.values or {}
    if not values or any(key not in values for key in ["enemy_team","first_outer_tower_time_ms","format_game_time","gap_change_text","gold_gap_delta_text","jungle_early_growth_story","jungle_gold_gap_at","jungle_growth_line","jungle_growth_swings","jungle_intervention_line","jungle_intervention_summary","jungle_interventions","objective_damage_share","objective_events","objective_fight_analysis","opponent_id","opponent_jungle_champion_name","participant_id","patch_label","raw_gold_compare_delta","role_matchup_header","target_team"]):
        return _placeholder_analysis_pages(ctx, "정글")
    if values.get("_smoke"):
        return _placeholder_analysis_pages(ctx, "정글")
    enemy_team = values["enemy_team"]
    first_outer_tower_time_ms = values["first_outer_tower_time_ms"]
    format_game_time = values["format_game_time"]
    gap_change_text = values["gap_change_text"]
    gold_gap_delta_text = values["gold_gap_delta_text"]
    jungle_early_growth_story = values["jungle_early_growth_story"]
    jungle_gold_gap_at = values["jungle_gold_gap_at"]
    jungle_growth_line = values["jungle_growth_line"]
    jungle_growth_swings = values["jungle_growth_swings"]
    jungle_intervention_line = values["jungle_intervention_line"]
    jungle_intervention_summary = values["jungle_intervention_summary"]
    jungle_interventions = values["jungle_interventions"]
    objective_damage_share = values["objective_damage_share"]
    objective_events = values["objective_events"]
    objective_fight_analysis = values["objective_fight_analysis"]
    opponent_id = values["opponent_id"]
    opponent_jungle_champion_name = values["opponent_jungle_champion_name"]
    participant_id = values["participant_id"]
    patch_label = values["patch_label"]
    raw_gold_compare_delta = values["raw_gold_compare_delta"]
    role_matchup_header = values["role_matchup_header"]
    target_team = values["target_team"]
    early_embed, operation_embed, combat_embed, weakness_embed = ctx.pages
    matchup = role_matchup_header("정글")
    cutoff_ms = first_outer_tower_time_ms()
    my_interventions = jungle_interventions(participant_id, target_team, cutoff_ms)
    enemy_interventions = jungle_interventions(opponent_id, enemy_team, cutoff_ms) if opponent_id else []

    early_embed.clear_fields()
    early_embed.title = f"🎯 정글 초반 영향력 - {patch_label}"
    early_embed.description = matchup
    if my_interventions:
        early_embed.add_field(
            name="🔥 초반 영향력",
            value="\n\n".join(jungle_intervention_line(row) for row in my_interventions[:4]),
            inline=False,
        )
    else:
        early_embed.add_field(name="🔥 초반 영향력", value="첫 1차 포탑 파괴 전 분석 가능한 라인 개입이 없습니다.", inline=False)
    early_embed.add_field(
        name="🗺️ 라인별 갱킹 결과",
        value=jungle_intervention_summary(my_interventions, enemy_interventions),
        inline=False,
    )
    early_embed.set_footer(text="1 / 4 · 초반 영향력")

    operation_embed.clear_fields()
    operation_embed.title = f"📈 정글 성장 - {patch_label}"
    operation_embed.description = matchup + "\n초반 성장 분석"
    early_growth_story = jungle_early_growth_story()
    if early_growth_story:
        operation_embed.add_field(
            name="🌲 초반 성장 격차",
            value=early_growth_story,
            inline=False,
        )
    growth_rows = jungle_growth_swings()
    if growth_rows:
        biggest_adv = max(growth_rows, key=lambda x: x["gd"])
        biggest_loss = min(growth_rows, key=lambda x: x["gd"])
        if biggest_adv["gd"] > 0:
            operation_embed.add_field(name="📈 내가 리드한 구간", value=jungle_growth_line(biggest_adv), inline=False)
        if biggest_loss["gd"] < 0:
            operation_embed.add_field(name="📉 내가 밀린 구간", value=jungle_growth_line(biggest_loss), inline=False)
        if biggest_adv["gd"] <= 0 and biggest_loss["gd"] >= 0:
            operation_embed.add_field(name="🌲 성장 격차", value="퀘스트 완료 전 큰 골드 격차 변화가 없습니다.", inline=False)
    else:
        operation_embed.add_field(name="🌲 성장 격차", value="상대 정글과 비교 가능한 구간 데이터가 부족합니다.", inline=False)
    operation_embed.set_footer(text="2 / 4 · 성장")

    combat_embed.clear_fields()
    combat_embed.title = f"🐉 정글 오브젝트 - {patch_label}"
    combat_embed.description = matchup
    if objective_events:
        objective_label_map = {"DRAGON":"드래곤","RIFT_HERALD":"전령","BARON":"바론","ELDER_DRAGON":"장로"}
        objective_lines = []
        for obj in sorted(objective_events, key=lambda item: int(item.get("time_ms",0) or 0))[:8]:
            obj_ms = int(obj.get("time_ms",0) or 0)
            ours = str(obj.get("team") or "") == target_team
            obj_name = objective_label_map.get(str(obj.get("name") or "").upper(), str(obj.get("name") or "오브젝트"))
            line = f"{'🟢' if ours else '🔴'} **{format_game_time(obj_ms)} · {obj_name} {'획득' if ours else '내줌'}**"
            analysis = objective_fight_analysis(obj)
            if analysis:
                before_gap = int(analysis.get("gold_gap_before",0) or 0)
                after_gap = int(analysis.get("gold_gap_after",0) or 0)
                team_delta = after_gap-before_gap
                jg_before = jungle_gold_gap_at(max(0, obj_ms-40_000))
                jg_after = jungle_gold_gap_at(obj_ms+25_000)
                if analysis["scene_type"] == "no_fight":
                    line += "\n└ ⚪ **무교전 확보**"
                    line += f"\n└ 🧮 팀 골드격차 {gold_gap_delta_text(before_gap, after_gap)}"
                    line += f"\n└ 🌲 {raw_gold_compare_delta(jg_before, jg_after, opponent_jungle_champion_name)}"
                elif analysis["scene_type"] == "other_fight":
                    other = analysis["other"]
                    line += f"\n└ 📍 **동시간대 다른 교전** · 킬 `{other['own_kills']}:{other['enemy_kills']}`"
                    line += f"\n└ 💰 {gap_change_text(team_delta)}"
                    line += f"\n└ 🌲 {raw_gold_compare_delta(jg_before, jg_after, opponent_jungle_champion_name)}"
                else:
                    linked = analysis["linked"]
                    line += f"\n└ ⚔️ **주변 교전 {linked['own_kills']}:{linked['enemy_kills']}** · {gap_change_text(team_delta)}"
                    share = objective_damage_share(obj_ms)
                    if share is not None:
                        line += f"\n└ 💥 교전 데미지 비중 **{share:.0f}%**"
                    elif not linked.get("target_involved"):
                        line += "\n└ 💥 본인 교전 미참여"
                    line += f"\n└ 🌲 {raw_gold_compare_delta(jg_before, jg_after, opponent_jungle_champion_name)}"
            objective_lines.append(line)

        chunks=[]; cur=[]; size=0
        for line in objective_lines:
            add=len(line)+(2 if cur else 0)
            if cur and (len(cur)>=2 or size+add>950): chunks.append(cur); cur=[]; size=0
            cur.append(line); size += len(line)+(2 if len(cur)>1 else 0)
        if cur: chunks.append(cur)
        for i, chunk in enumerate(chunks,1):
            combat_embed.add_field(name="🐉 오브젝트 분석" if len(chunks)==1 else f"🐉 오브젝트 분석 · {i}/{len(chunks)}", value="\n\n".join(chunk), inline=False)
    else:
        combat_embed.add_field(name="🐉 오브젝트 분석", value="시간대별 오브젝트 이벤트를 복원하지 못했습니다.", inline=False)
    combat_embed.set_footer(text="3 / 4 · 오브젝트")

    weakness_embed.clear_fields()
    weakness_embed.title = f"📋 정글 총정리 - {patch_label}"
    weakness_embed.description = matchup
    jungle_good=[]; jungle_fix=[]
    if my_interventions:
        total_lane = sum(int(x.get("lane_benefit",0) or 0) for x in my_interventions if x.get("lane") != "기타")
        total_cost = sum(int(x.get("jungle_cost",0) or 0) for x in my_interventions)
        if total_lane >= 500:
            jungle_good.append(f"🗺️ **초반 라인 개입 효과** · 첫 포탑 전 개입으로 라인 골드차를 누적 약 `{total_lane:,}G` 유리하게 만들었습니다.")
        elif total_lane <= -500:
            jungle_fix.append(f"🗺️ **개입 후 라인 이득이 남지 않았습니다.** 개입 구간들의 이후 2분 라인 골드차가 누적 `{total_lane:+,}G`였습니다. 킬 이후 웨이브/플레이트 연결을 확인할 필요가 있습니다.")
        if total_cost <= -500:
            jungle_fix.append(f"🌲 **개입 비용으로 정글 성장 손실** · 갱킹 구간 합산 `vs {opponent_jungle_champion_name}` 골드차이 `{total_cost:+,}G`. 개입 성공률과 캠프 손실을 같이 봐야 합니다.")
        elif total_cost >= 500:
            jungle_good.append(f"🌲 **개입과 성장 동시 확보** · 갱킹 구간 합산 `vs {opponent_jungle_champion_name}` 골드차이 `{total_cost:+,}G`.")
    if growth_rows:
        best=max(growth_rows,key=lambda x:x['gd']); worst=min(growth_rows,key=lambda x:x['gd'])
        if best['gd']>=500: jungle_good.append(f"📈 **{best['from']}~{best['to']}분 정글 성장 우위** · `vs {opponent_jungle_champion_name}` 골드차이 `{best['gd']:+,}G`.")
        if worst['gd']<=-500: jungle_fix.append(f"📉 **{worst['from']}~{worst['to']}분 성장 손실** · `vs {opponent_jungle_champion_name}` 골드차이 `{worst['gd']:+,}G`. 캠프 동선과 개입 시간을 함께 복기하는 것이 좋습니다.")
    if not jungle_good: jungle_good.append("뚜렷한 강점은 초반 개입·성장·오브젝트 장면을 더 확인하면 좋습니다.")
    if not jungle_fix: jungle_fix.append("큰 손실로 분류된 구간이 적습니다. 개입 후 2분 라인 이득이 실제로 유지됐는지 장면 단위로 확인하면 좋습니다.")
    weakness_embed.add_field(name="✨ 좋은점", value="\n\n".join(jungle_good[:4]), inline=False)
    weakness_embed.add_field(name="🛠️ 보완점", value="\n\n".join(jungle_fix[:4]), inline=False)
    weakness_embed.set_footer(text="4 / 4 · 총정리")

    return [early_embed, operation_embed, combat_embed, weakness_embed]

def build_mid_analysis_pages(ctx):
    values = ctx.values or {}
    if not values or any(key not in values for key in ["add_compact_impact_highlights","add_fight_log","add_lane_tactical_field","fight_deaths","fight_losses","fight_wins","involved_fights","opponent_id","participant_id","patch_label","role_matchup_header","target_team"]):
        return _placeholder_analysis_pages(ctx, "미드")
    if values.get("_smoke"):
        return _placeholder_analysis_pages(ctx, "미드")
    add_compact_impact_highlights = values["add_compact_impact_highlights"]
    add_fight_log = values["add_fight_log"]
    add_lane_tactical_field = values["add_lane_tactical_field"]
    fight_deaths = values["fight_deaths"]
    fight_losses = values["fight_losses"]
    fight_wins = values["fight_wins"]
    involved_fights = values["involved_fights"]
    opponent_id = values["opponent_id"]
    participant_id = values["participant_id"]
    patch_label = values["patch_label"]
    role_matchup_header = values["role_matchup_header"]
    target_team = values["target_team"]
    early_embed, operation_embed, combat_embed, weakness_embed = ctx.pages
    early_embed.title = f"🌱 미드 성장 분석 - {patch_label}"
    early_embed.description = role_matchup_header("미드")
    add_lane_tactical_field(early_embed, "MID")
    early_embed.set_footer(text="1 / 4 · 성장 분석")
    
    operation_embed.clear_fields()
    operation_embed.title = f"🎯 미드 킬 영향력 - {patch_label}"
    operation_embed.description = role_matchup_header("미드")
    add_compact_impact_highlights(
        operation_embed, participant_id, target_team,
        counterpart_pid=opponent_id, counterpart_label="상대 미드",
        field_name="🔥 영향력이 컸던 킬 관여", limit=3,
    )
    operation_embed.set_footer(text="2 / 4 · 킬 영향력")
    
    combat_embed.clear_fields()
    combat_embed.title = f"⚔️ 미드 교전력 - {patch_label}"
    combat_embed.add_field(
        name="📊 교전 요약",
        value=(
            f"참여 `{len(involved_fights)}`회 · 팀 `{fight_wins}승 {fight_losses}패` · "
            f"사망 `{fight_deaths}`회"
        ), inline=False,
    )
    add_fight_log(combat_embed)
    combat_embed.set_footer(text="3 / 4 · 교전력")
    
    return [early_embed, operation_embed, combat_embed, weakness_embed]

def build_adc_analysis_pages(ctx):
    values = ctx.values or {}
    if not values or any(key not in values for key in ["add_lane_tactical_field","avg_measured_dpm","combat_metric_series","final_row","format_game_time","gold_swing_text","involved_fights","measured_dpm_rows","patch_label","role_matchup_header","rofl_combat_checkpoint"]):
        return _placeholder_analysis_pages(ctx, "원딜")
    if values.get("_smoke"):
        return _placeholder_analysis_pages(ctx, "원딜")
    add_lane_tactical_field = values["add_lane_tactical_field"]
    avg_measured_dpm = values["avg_measured_dpm"]
    combat_metric_series = values["combat_metric_series"]
    final_row = values["final_row"]
    format_game_time = values["format_game_time"]
    gold_swing_text = values["gold_swing_text"]
    involved_fights = values["involved_fights"]
    measured_dpm_rows = values["measured_dpm_rows"]
    patch_label = values["patch_label"]
    role_matchup_header = values["role_matchup_header"]
    rofl_combat_checkpoint = values["rofl_combat_checkpoint"]
    early_embed, operation_embed, combat_embed, weakness_embed = ctx.pages
    early_embed.title = f"🌱 원딜 성장 - {patch_label}"
    early_embed.description = role_matchup_header("원딜")
    add_lane_tactical_field(early_embed, "BOT")
    early_embed.set_footer(text="1 / 4 · 성장")
    
    operation_embed.clear_fields()
    operation_embed.title = f"💥 원딜 한타 DPM - {patch_label}"
    operation_embed.description = role_matchup_header("원딜")
    if measured_dpm_rows:
        dpm_lines = []
        for row in measured_dpm_rows[:5]:
            fight = row["fight"]
            dpm_lines.append(
                f"• {format_game_time(fight['start_ms'])} · `{fight['outcome']}` · "
                f"측정구간 DPM `{int(round(row['dpm'])):,}` · 챔피언딜 `{int(round(row['dealt'])):,}`"
            )
        operation_embed.add_field(
            name="🔥 교전별 DPM",
            value="\n".join(dpm_lines), inline=False,
        )
        operation_embed.add_field(
            name="📊 측정구간 평균",
            value=f"평균 DPM `{int(round(avg_measured_dpm)):,}` · 측정 가능 교전 `{len(measured_dpm_rows)}`회",
            inline=False,
        )
    else:
        if not involved_fights:
            dpm_status = "3인 이상 교전에 직접 참여한 기록이 없습니다."
        elif rofl_combat_checkpoint is None:
            dpm_status = f"교전 `{len(involved_fights)}`회 감지 · DPM 체크포인트 모듈을 불러오지 못했습니다."
        elif not combat_metric_series:
            dpm_status = f"교전 `{len(involved_fights)}`회 감지 · 해당 참가자의 DPM 체크포인트를 연결하지 못했습니다."
        else:
            dpm_status = (
                f"교전 `{len(involved_fights)}`회 감지 · "
                "이번 리플레이에서는 교전을 감싸는 유효 DPM 측정구간을 만들지 못했습니다."
            )
        operation_embed.add_field(name="📌 DPM", value=dpm_status, inline=False)
    operation_embed.set_footer(text="2 / 4 · 한타 DPM")
    
    combat_embed.clear_fields()
    combat_embed.title = f"💀 원딜 데스 효율 - {patch_label}"
    combat_embed.description = role_matchup_header("원딜")
    death_fights = [fight for fight in involved_fights if int(fight.get("target_d", 0) or 0) > 0]
    measured_by_fight = {id(row.get("fight")): row for row in measured_dpm_rows if row.get("fight") is not None}
    if death_fights:
        lines = []
        measured_death_damage = []
        for fight in death_fights[:5]:
            metric = measured_by_fight.get(id(fight))
            if metric:
                dealt = int(round(float(metric.get("dealt", 0) or 0)))
                dpm = int(round(float(metric.get("dpm", 0) or 0)))
                measured_death_damage.append(dealt)
                damage_text = f"딜 `{dealt:,}` · DPM `{dpm:,}`"
            else:
                damage_text = "딜 `측정구간 없음`"
            takedowns = int(fight.get("target_k", 0) or 0) + int(fight.get("target_a", 0) or 0)
            lines.append(
                f"• **{format_game_time(fight['start_ms'])}** · {damage_text} · 킬관여 `{takedowns}` · "
                f"팀 `{gold_swing_text(fight['gold_gap_delta'])}`"
            )
        combat_embed.add_field(name="💥 사망 교전에서 넣은 딜", value="\n".join(lines), inline=False)
    
        final_damage = int((final_row or {}).get("damage_to_champions", 0) or 0)
        final_deaths = 0
        if final_row:
            try:
                final_deaths = int((final_row.get("rofl_stats") or {}).get("DEATHS", final_row.get("deaths", 0)) or 0)
            except (TypeError, ValueError):
                final_deaths = int(final_row.get("deaths", 0) or 0)
        if final_deaths > 0 and final_damage > 0:
            per_death = int(round(final_damage / final_deaths))
            combat_embed.add_field(
                name="📊 데스당 피해량",
                value=(
                    f"경기 전체 챔피언 피해 `{final_damage:,}` ÷ 데스 `{final_deaths}` = **`{per_death:,}`**\n"
                    "티어 평균 비교는 데이터 축적 후 추가 예정"
                ),
                inline=False,
            )
        elif measured_death_damage:
            avg_before_death = int(round(sum(measured_death_damage) / len(measured_death_damage)))
            combat_embed.add_field(
                name="📊 사망 교전 평균 피해",
                value=f"측정 가능한 사망 교전 `{len(measured_death_damage)}`회 · 평균 `{avg_before_death:,}`",
                inline=False,
            )
    else:
        combat_embed.add_field(
            name="💀 사망 교전",
            value="감지된 3인 이상 교전에서는 사망하지 않았습니다.",
            inline=False,
        )
    combat_embed.set_footer(text="3 / 4 · 데스 효율")
    
    return [early_embed, operation_embed, combat_embed, weakness_embed]

def build_support_analysis_pages(ctx):
    values = ctx.values or {}
    if not values or any(key not in values for key in ["add_fight_log","add_impact_highlights","add_lane_tactical_field","add_tower_timeline","champion","early","enemy_team","fight_deaths","fight_losses","fight_survival_rate","fight_takedowns","fight_wins","final_row","interval_participation","involved_fights","level_from_xp","max_game_minute","opponent_final_row","opponent_id","participant_id","patch_label","player_name","role","role_matchup_header","stats_for_row","target_team"]):
        return _placeholder_analysis_pages(ctx, "서폿")
    if values.get("_smoke"):
        return _placeholder_analysis_pages(ctx, "서폿")
    add_fight_log = values["add_fight_log"]
    add_impact_highlights = values["add_impact_highlights"]
    add_lane_tactical_field = values["add_lane_tactical_field"]
    add_tower_timeline = values["add_tower_timeline"]
    champion = values["champion"]
    early = values["early"]
    enemy_team = values["enemy_team"]
    fight_deaths = values["fight_deaths"]
    fight_losses = values["fight_losses"]
    fight_survival_rate = values["fight_survival_rate"]
    fight_takedowns = values["fight_takedowns"]
    fight_wins = values["fight_wins"]
    final_row = values["final_row"]
    interval_participation = values["interval_participation"]
    involved_fights = values["involved_fights"]
    level_from_xp = values["level_from_xp"]
    max_game_minute = values["max_game_minute"]
    opponent_final_row = values["opponent_final_row"]
    opponent_id = values["opponent_id"]
    participant_id = values["participant_id"]
    patch_label = values["patch_label"]
    player_name = values["player_name"]
    role = values["role"]
    role_matchup_header = values["role_matchup_header"]
    stats_for_row = values["stats_for_row"]
    target_team = values["target_team"]
    early_embed, operation_embed, combat_embed, weakness_embed = ctx.pages
    early_embed.clear_fields()
    early_embed.title = f"🤝 서포터 라인전 능력 - {patch_label}"
    early_embed.description = f"🎮 **{player_name}**\n💫 `{role}` · **{champion}** · CS 제외"
    add_lane_tactical_field(early_embed, "BOT")
    early_lane = interval_participation(participant_id, target_team, 0, 15)
    opp_early_lane = interval_participation(opponent_id, enemy_team, 0, 15) if opponent_id else {}
    add_impact_highlights(
        early_embed, participant_id, target_team,
        counterpart_pid=opponent_id, counterpart_label="상대 서폿",
        start_ms=0, end_ms=15 * 60_000,
        field_name="🤝 라인전에서 이득으로 이어진 관여", limit=3,
    )
    lane_lines = [
        f"💀 사망 `{early_lane.get('deaths', 0)}`회 vs 상대 `{opp_early_lane.get('deaths', 0)}`회",
    ]
    if early:
        last = early[-1]
        if last.get("opp"):
            lane_lines.append(
                f"⬆️ 레벨 `{level_from_xp(last['row'].get('xp', 0))}` vs 상대 `{level_from_xp(last['opp'].get('xp', 0))}`"
            )
            lane_lines.append(
                f"💰 골드 `{int(last['row'].get('total_gold', 0) or 0):,}G` vs 상대 "
                f"`{int(last['opp'].get('total_gold', 0) or 0):,}G`"
            )
    early_embed.add_field(name="📊 15분 시점", value="\n".join(lane_lines), inline=False)
    early_embed.set_footer(text="1 / 4 · 라인전 능력")
    
    operation_embed.clear_fields()
    operation_embed.title = f"👁️ 서포터 시야 싸움 - {patch_label}"
    operation_embed.description = role_matchup_header("서폿")
    rs = stats_for_row(final_row)
    ors = stats_for_row(opponent_final_row)
    vision_rows = [
        ("👁️ 시야 점수", "VISION_SCORE"),
        ("🟢 와드 설치", "WARD_PLACED"),
        ("🧹 와드 제거", "WARD_KILLED"),
        ("🟥 제어 와드 구매", "VISION_WARDS_BOUGHT_IN_GAME"),
    ]
    vision_lines = []
    for label, key in vision_rows:
        mine = int(float(rs.get(key, 0) or 0))
        theirs = int(float(ors.get(key, 0) or 0)) if opponent_final_row else None
        vision_lines.append(f"{label} `{mine}`" + (f" vs 상대 `{theirs}`" if theirs is not None else ""))
    operation_embed.add_field(name="🔭 경기 전체 시야", value="\n".join(vision_lines), inline=False)
    
    # Ward placement/removal timestamps are not yet decoded safely from
    # this ROFL build. Split the support's *map involvement* by phase
    # instead of fabricating per-phase ward counts.
    phase_specs = [
        ("0 ~ 15분", 0, 15),
        ("15 ~ 20분", 15, 20),
        ("20분 이후", 20, max_game_minute),
    ]
    phase_lines = []
    for phase_label, phase_start, phase_end in phase_specs:
        if phase_end <= phase_start:
            continue
        mine = interval_participation(participant_id, target_team, phase_start, phase_end)
        theirs = interval_participation(opponent_id, enemy_team, phase_start, phase_end) if opponent_id else {}
        phase_lines.append(
            f"**{phase_label}** · 킬관여 `{mine.get('takedowns', 0)}`회 · 사망 `{mine.get('deaths', 0)}`회 "
            f"vs 상대 킬관여 `{theirs.get('takedowns', 0)}`회 · 사망 `{theirs.get('deaths', 0)}`회"
        )
    if phase_lines:
        operation_embed.add_field(
            name="🗺️ 시간대별 맵 관여",
            value="\n".join(phase_lines),
            inline=False,
        )
    operation_embed.set_footer(text="2 / 4 · 시야 싸움")
    
    combat_embed.clear_fields()
    combat_embed.title = f"🎯 서포터 영향력 - {patch_label}"
    combat_embed.description = role_matchup_header("서폿")
    combat_embed.add_field(
        name="🤝 교전 합류 / 생존",
        value=(
            f"참여 교전 `{len(involved_fights)}`회 · 팀 `{fight_wins}승 {fight_losses}패`\n"
            f"교전 킬관여 `{fight_takedowns}`회 · 사망 `{fight_deaths}`회 · 생존률 `{fight_survival_rate:.0f}%`"
        ), inline=False,
    )
    # Exact CC hit counts are deliberately not shown yet. The current
    # cumulative CC counter cannot safely distinguish hit count/type.
    add_fight_log(combat_embed, include_damage=False)
    add_tower_timeline(combat_embed, limit=4)
    combat_embed.set_footer(text="3 / 4 · 영향력")
    
    return [early_embed, operation_embed, combat_embed, weakness_embed]


# ---------------------------------------------------------------------------
# Coaching report v2: one visual grammar, role-specific early cutoff.
# These definitions intentionally override the older role-specific report
# builders above. The decoder/data layer is unchanged.
# ---------------------------------------------------------------------------
def _build_coaching_role_pages(ctx, role_name):
    values = ctx.values or {}
    required = (
        "analysis_early_cutoff_text", "analysis_early_summary", "analysis_early_detail", "analysis_key_fights",
        "analysis_fight_line", "analysis_swing_points", "analysis_death_mistakes",
        "analysis_objective_points", "role_matchup_header", "format_game_time",
    )
    if not values or any(key not in values for key in required):
        return _placeholder_analysis_pages(ctx, role_name)
    if values.get("_smoke"):
        return _placeholder_analysis_pages(ctx, role_name)

    early_cutoff_text = values["analysis_early_cutoff_text"]
    early_summary = values["analysis_early_summary"]
    early_detail = values["analysis_early_detail"]
    key_fights = values["analysis_key_fights"]
    fight_line = values["analysis_fight_line"]
    swing_points = values["analysis_swing_points"]
    death_mistakes = values["analysis_death_mistakes"]
    objective_points = values["analysis_objective_points"]
    matchup_header = values["role_matchup_header"]
    format_game_time = values["format_game_time"]

    patch_label = str(ctx.patch_display_label or values.get("patch_label") or "")
    if patch_label and not patch_label.endswith("패치"):
        patch_label += " 패치"
    matchup = matchup_header(role_name)
    early_embed, fight_embed, turning_embed, summary_embed = ctx.pages

    # Page 1. The user sees only the intuitive outcome. XP stays internal and
    # is translated to champion level for the report.
    early_embed.clear_fields()
    early_embed.title = f"🌱 {role_name} 초반 - {patch_label}".strip()
    early_embed.description = matchup
    early_embed.add_field(
        name="⏱️ 초반 종료 기준",
        value=early_cutoff_text(role_name),
        inline=False,
    )
    early_embed.add_field(
        name="📊 종료 시점 성장 격차",
        value=early_summary(role_name),
        inline=False,
    )
    detail = early_detail(role_name)
    if detail:
        early_embed.add_field(
            name="🔎 초반 포인트",
            value=detail,
            inline=False,
        )
    early_embed.set_footer(text="1 / 4 · 초반")

    # Page 2. Only the fights that matter enough to revisit are surfaced.
    fight_embed.clear_fields()
    fight_embed.title = f"⚔️ {role_name} 주요 교전 - {patch_label}".strip()
    fight_embed.description = matchup + "\n초반 종료 이후 · 본인 참여 교전 중 오브젝트 인접/골드 변화가 큰 장면만 표시"
    fights = key_fights(role_name, limit=4)
    if fights:
        fight_embed.add_field(
            name="🔥 복기할 교전",
            value="\n\n".join(fight_line(role_name, fight, obj) for fight, obj in fights),
            inline=False,
        )
    else:
        fight_embed.add_field(
            name="🔥 복기할 교전",
            value="조건에 맞는 주요 교전이 없습니다.",
            inline=False,
        )
    fight_embed.set_footer(text="2 / 4 · 주요 교전")

    # Page 3. Translate events into consequences: two-minute team-gold swing,
    # objective-fight contribution, and deaths that actually cost the team.
    turning_embed.clear_fields()
    turning_embed.title = f"🧠 {role_name} 승부 포인트 - {patch_label}".strip()
    turning_embed.description = matchup

    obj_rows = objective_points(role_name, limit=3)
    if obj_rows:
        lines = []
        for row in obj_rows:
            fight = row["fight"]
            side = "획득" if str((row.get("obj") or {}).get("team") or "") == str(ctx.target_team) else "내줌"
            line = (
                f"• **{format_game_time((row.get('obj') or {}).get('time_ms', 0))} · {row['name']} {side}**\n"
                f"  └ 교전 `{fight.get('own_kills',0)}:{fight.get('enemy_kills',0)}` · "
                f"2분 골드차 `{row['before']:+,}G → {row['after']:+,}G`"
            )
            if role_name != "서폿" and fight.get("target_damage_share") is not None:
                line += f"\n  └ 본인 팀 교전딜 비중 **{float(fight['target_damage_share']):.0f}%**"
            elif role_name == "서폿":
                takedowns = int(fight.get("target_k",0) or 0) + int(fight.get("target_a",0) or 0)
                line += f"\n  └ 본인 킬관여 `{takedowns}` · 데스 `{int(fight.get('target_d',0) or 0)}`"
            lines.append(line)
        turning_embed.add_field(name="🐉 오브젝트 교전", value="\n\n".join(lines), inline=False)

    swings = swing_points(role_name, limit=3)
    if swings:
        lines = []
        for row in swings:
            arrow = "📈" if row["delta"] > 0 else "📉"
            lines.append(
                f"{arrow} **{format_game_time(row['fight'].get('start_ms',0))}** · "
                f"교전 시작 `{row['before']:+,}G` → 2분 뒤 `{row['after']:+,}G` "
                f"(**{row['delta']:+,}G 변화**)"
            )
        turning_embed.add_field(name="💰 흐름을 크게 바꾼 교전", value="\n".join(lines), inline=False)

    mistakes = death_mistakes(role_name, limit=2)
    if mistakes:
        obj_names = {"DRAGON":"드래곤", "RIFT_HERALD":"전령", "BARON":"바론", "ELDER_DRAGON":"장로"}
        lines = []
        for row in mistakes:
            losses = []
            for obj in row["objectives"]:
                losses.append(obj_names.get(str(obj.get("name") or "").upper(), "오브젝트"))
            if row["towers"]:
                losses.append(f"포탑 {len(row['towers'])}개")
            loss_text = " · ".join(losses) if losses else "추가 구조물/오브젝트 손실 없음"
            lines.append(
                f"💀 **{format_game_time(row['fight'].get('start_ms',0))} 데스**\n"
                f"  └ 팀 골드차 `{row['before']:+,}G → {row['after']:+,}G` · {loss_text}"
            )
        turning_embed.add_field(name="🚨 내 데스로 크게 흔들린 지점", value="\n\n".join(lines), inline=False)

    if not obj_rows and not swings and not mistakes:
        turning_embed.add_field(
            name="📌 승부 포인트",
            value="큰 골드 전환이나 데스 후 연쇄 손실로 분류되는 장면이 없습니다.",
            inline=False,
        )
    turning_embed.set_footer(text="3 / 4 · 승부 포인트")

    # Page 4. Keep the conclusion short. The report should tell the user what
    # to revisit, not repeat every number from the prior pages.
    summary_embed.clear_fields()
    summary_embed.title = f"📋 {role_name} 총정리 - {patch_label}".strip()
    summary_embed.description = matchup
    early_text = early_summary(role_name)
    summary_embed.add_field(name="🌱 초반", value=early_text, inline=False)

    good = [row for row in swings if row["delta"] > 0]
    bad = [row for row in swings if row["delta"] < 0]
    if good:
        best = max(good, key=lambda row: row["delta"])
        summary_embed.add_field(
            name="✅ 가장 좋았던 전환",
            value=(
                f"**{format_game_time(best['fight'].get('start_ms',0))} 교전** 이후 2분 동안 "
                f"팀 골드 흐름을 **{best['delta']:+,}G** 개선했습니다."
            ), inline=False,
        )
    if mistakes:
        worst = mistakes[0]
        summary_embed.add_field(
            name="🛠️ 가장 먼저 복기할 장면",
            value=(
                f"**{format_game_time(worst['fight'].get('start_ms',0))} 데스** 이후 "
                f"팀 골드 흐름이 **{worst['delta']:+,}G** 변했습니다. "
                "사망 직전 위치와 교전 진입 판단을 먼저 확인하세요."
            ), inline=False,
        )
    elif bad:
        worst = min(bad, key=lambda row: row["delta"])
        summary_embed.add_field(
            name="🛠️ 가장 먼저 복기할 장면",
            value=(
                f"**{format_game_time(worst['fight'].get('start_ms',0))} 교전** 이후 2분 동안 "
                f"팀 골드 흐름이 **{worst['delta']:+,}G** 악화됐습니다."
            ), inline=False,
        )
    else:
        summary_embed.add_field(
            name="🛠️ 복기 우선순위",
            value="큰 손실로 분류된 장면이 적습니다. 주요 교전 탭의 장면부터 확인하면 됩니다.",
            inline=False,
        )
    summary_embed.set_footer(text="4 / 4 · 총정리")
    return [early_embed, fight_embed, turning_embed, summary_embed]


def build_top_analysis_pages(ctx):
    return _build_coaching_role_pages(ctx, "탑")


def build_jungle_analysis_pages(ctx):
    return _build_coaching_role_pages(ctx, "정글")


def build_mid_analysis_pages(ctx):
    return _build_coaching_role_pages(ctx, "미드")


def build_adc_analysis_pages(ctx):
    return _build_coaching_role_pages(ctx, "원딜")


def build_support_analysis_pages(ctx):
    return _build_coaching_role_pages(ctx, "서폿")


async def send_match_analysis_pages(interaction, pages, labels, player_name="", patch_display_label=""):
    """Send the pager separately from replay decoding and page construction."""

    class MatchAnalysisPager(discord.ui.View):
        def __init__(self, owner_id: int):
            super().__init__(timeout=3600)
            self.owner_id = int(owner_id)
            self.page = 0
            for index, label in enumerate(labels or ()):
                if index < len(self.children) and isinstance(self.children[index], discord.ui.Button):
                    self.children[index].label = label
            self._sync()

        def _sync(self):
            for index, child in enumerate(self.children):
                if isinstance(child, discord.ui.Button):
                    child.style = discord.ButtonStyle.primary if index == self.page else discord.ButtonStyle.secondary

        async def interaction_check(self, page_interaction: discord.Interaction) -> bool:
            if int(page_interaction.user.id) != self.owner_id:
                await page_interaction.response.send_message(
                    "이 분석을 실행한 사용자만 페이지를 변경할 수 있습니다.",
                    ephemeral=True,
                )
                return False
            return True

        async def _show(self, page_interaction: discord.Interaction, page: int):
            self.page = page
            self._sync()
            await page_interaction.response.edit_message(embed=pages[self.page], view=self)

        @discord.ui.button(label="🌱 성장", style=discord.ButtonStyle.primary)
        async def growth(self, page_interaction: discord.Interaction, button: discord.ui.Button):
            await self._show(page_interaction, 0)

        @discord.ui.button(label="🧭 운영", style=discord.ButtonStyle.secondary)
        async def operation(self, page_interaction: discord.Interaction, button: discord.ui.Button):
            await self._show(page_interaction, 1)

        @discord.ui.button(label="⚔️ 교전", style=discord.ButtonStyle.secondary)
        async def combat(self, page_interaction: discord.Interaction, button: discord.ui.Button):
            await self._show(page_interaction, 2)

        @discord.ui.button(label="🩹 약점", style=discord.ButtonStyle.secondary)
        async def weakness(self, page_interaction: discord.Interaction, button: discord.ui.Button):
            await self._show(page_interaction, 3)

    await interaction.followup.send(
        embed=pages[0],
        view=MatchAnalysisPager(interaction.user.id),
        ephemeral=True,
    )


def run_match_analysis_role_smoke_tests():
    """Build all five production role builders without Discord I/O or writes."""

    labels = {
        key: ("🌱 초반", "⚔️ 주요 교전", "🧠 승부 포인트", "📋 총정리")
        for key in ("탑", "정글", "미드", "원딜", "서폿")
    }
    builders = {
        "탑": build_top_analysis_pages,
        "정글": build_jungle_analysis_pages,
        "미드": build_mid_analysis_pages,
        "원딜": build_adc_analysis_pages,
        "서폿": build_support_analysis_pages,
    }
    def _field(embed, *args, **kwargs):
        embed.add_field(name="🧪 smoke", value="production builder", inline=False)

    def _interval(*args, **kwargs):
        return {"takedowns": 0, "team_kills": 0, "rate": 0, "deaths": 0}

    def _matchup_header(role_name=None):
        return f"⚔️ **{role_name or '라인'} · 테스트 챔피언 vs 상대 챔피언**"

    values = {
        "_team_gold_gap_from_series": lambda *args, **kwargs: 0,
        "champion": "테스트 챔피언",
        "format_game_time": lambda value: "0분 00초",
        "gold_gap_delta_text": lambda *args, **kwargs: "골드차이 변화 없음",
        "gold_gap_state": lambda value: "골드차이 0G",
        "opponent_champion_name": "상대 챔피언",
        "opponent_id": 6,
        "participant_id": 1,
        "patch_label": "16.16",
        "quest_time_ms": lambda *args, **kwargs: 0,
        "series_after_ms": lambda *args, **kwargs: None,
        "series_before_ms": lambda *args, **kwargs: None,
        "target_team": "blue",
        "top_enemy_outer_tower": lambda: None,
        "top_fight_line": lambda *args, **kwargs: "smoke",
        "top_lane_2v2_fights": lambda *args, **kwargs: [],
        "top_post_tower_objective_lines": lambda *args, **kwargs: [],
        "top_prequest_swings": lambda: [],
        "top_quest_compare_text": lambda: "smoke",
        "top_side_operation_text": lambda *args, **kwargs: "smoke",
        "top_swing_text": lambda *args, **kwargs: "smoke",
        "enemy_team": "red",
        "first_outer_tower_time_ms": lambda: 900_000,
        "gap_change_text": lambda *args, **kwargs: "smoke",
        "jungle_early_growth_story": lambda: None,
        "jungle_gold_gap_at": lambda *args, **kwargs: 0,
        "jungle_growth_line": lambda *args, **kwargs: "smoke",
        "jungle_growth_swings": lambda: [],
        "jungle_intervention_line": lambda *args, **kwargs: "smoke",
        "jungle_intervention_summary": lambda *args, **kwargs: "smoke",
        "jungle_interventions": lambda *args, **kwargs: [],
        "objective_damage_share": lambda *args, **kwargs: None,
        "objective_events": [],
        "objective_fight_analysis": lambda *args, **kwargs: None,
        "opponent_jungle_champion_name": "상대 정글",
        "raw_gold_compare_delta": lambda *args, **kwargs: "smoke",
        "role_matchup_header": _matchup_header,
        "add_compact_impact_highlights": _field,
        "add_fight_log": _field,
        "add_lane_tactical_field": _field,
        "fight_deaths": 0,
        "fight_losses": 0,
        "fight_wins": 0,
        "involved_fights": [],
        "avg_measured_dpm": 0,
        "combat_metric_series": [],
        "final_row": {},
        "gold_swing_text": lambda *args, **kwargs: "smoke",
        "measured_dpm_rows": [],
        "rofl_combat_checkpoint": None,
        "add_impact_highlights": _field,
        "add_tower_timeline": _field,
        "early": [],
        "fight_survival_rate": 0,
        "fight_takedowns": 0,
        "interval_participation": _interval,
        "level_from_xp": lambda value: 1,
        "max_game_minute": 30,
        "opponent_final_row": None,
        "player_name": "smoke#TEST",
        "role": "미지정",
        "stats_for_row": lambda row: {},
        "analysis_early_cutoff_text": lambda role_name: "**12분 00초** · 테스트 초반 종료",
        "analysis_early_summary": lambda role_name: "**비슷** · 💰 골드 `+0G` · ⬆️ 레벨 `8 vs 8`",
        "analysis_early_detail": lambda role_name: "🎯 테스트 초반 포인트",
        "analysis_key_fights": lambda role_name, limit=4: [],
        "analysis_fight_line": lambda role_name, fight, obj=None: "smoke fight",
        "analysis_swing_points": lambda role_name, limit=3: [],
        "analysis_death_mistakes": lambda role_name, limit=2: [],
        "analysis_objective_points": lambda role_name, limit=3: [],
    }
    role_markers = {"탑": "탑", "정글": "정글", "미드": "미드", "원딜": "원딜", "서폿": "서포터"}
    result = {}
    for role, page_labels in labels.items():
        pages = [discord.Embed() for _ in range(4)]
        context_values = dict(values)
        context_values["role"] = role
        context = MatchAnalysisContext(
            player_name="smoke#TEST",
            role=role,
            champion="테스트 챔피언",
            opponent_champion="상대 챔피언",
            patch_label="16.16",
            patch_display_label="26.16",
            pages=pages,
            page_labels=page_labels,
            values=context_values,
        )
        built = builders[role](context)
        assert len(built) == 4, role
        assert all(isinstance(page, discord.Embed) for page in built), role
        assert built[0].title and role_markers[role] in built[0].title, role
        result[role] = built

    matchup = resolve_analysis_matchup(
        {"participant_id": 1, "team": "blue", "role": "탑", "champion": "테스트 챔피언"},
        [
            {"participant_id": 1, "team": "blue", "role": "탑", "champion": "테스트 챔피언"},
            {"participant_id": 6, "team": "red", "role": "TOP", "champion": "상대 챔피언"},
        ],
    )
    assert matchup["opponent_id"] == 6
    assert matchup["opponent_champion_name"] == "상대 챔피언"
    return result


async def load_match_analysis_context(
    interaction,
    파일,
    닉네임태그,
    *,
    helper_scope=None,
):
    """Decode one ROFL and build role pages without Discord I/O."""

    helper_scope = helper_scope or {}
    required_helpers = (
        "get_rofl_champion_map",
        "validate_rofl_upload_size",
        "run_rofl_analysis_once",
        "normalize_rofl_match_name",
        "resolve_rofl_input_riot_id",
    )
    missing_helpers = [name for name in required_helpers if not callable(helper_scope.get(name))]
    if missing_helpers:
        raise RuntimeError("경기분석 loader helper 누락: " + ", ".join(missing_helpers))
    get_rofl_champion_map = helper_scope["get_rofl_champion_map"]
    validate_rofl_upload_size = helper_scope["validate_rofl_upload_size"]
    run_rofl_analysis_once = helper_scope["run_rofl_analysis_once"]
    normalize_rofl_match_name = helper_scope["normalize_rofl_match_name"]
    resolve_rofl_input_riot_id = helper_scope["resolve_rofl_input_riot_id"]

    validate_rofl_upload_size(파일)
    raw = await 파일.read()
    if not raw:
        raise ValueError("업로드된 ROFL 파일이 비어 있습니다.")
    validate_rofl_upload_size(파일, raw)
    
    try:
        champion_map = await asyncio.wait_for(asyncio.to_thread(get_rofl_champion_map), timeout=6)
    except Exception as exc:
        logger.warning("ROFL champion map load timed out or failed: %s", exc)
        champion_map = None
    
    rofl_rows = await asyncio.to_thread(rofl.read_rofl_player_stats_from_bytes, raw, champion_map)

    # `블루` / `레드` is a first-class team-analysis target. Personal analysis
    # keeps accepting the old Riot-ID input in the same command.
    _analysis_target = str(닉네임태그 or "").strip()
    _team_aliases = {
        "블루": "blue", "블루팀": "blue", "blue": "blue", "blueteam": "blue",
        "레드": "red", "레드팀": "red", "red": "red", "redteam": "red",
    }
    _team_target = _team_aliases.get(_analysis_target.lower().replace(" ", ""))
    resolved_riot_id = None
    duplicate_name_matches = []
    if not _team_target:
        resolved_riot_id, duplicate_name_matches = resolve_rofl_input_riot_id(rofl_rows, 닉네임태그)
        if not resolved_riot_id:
            if duplicate_name_matches:
                raise ValueError(
                    "같은 닉네임의 참가자가 둘 이상입니다. 태그까지 입력해주세요: "
                    + ", ".join(duplicate_name_matches)
                )
            names = ", ".join(str(row.get("summoner_name") or "?") for row in rofl_rows[:10])
            raise ValueError(
                f"분석대상 `{_analysis_target}`을 찾지 못했습니다. "
                "팀 분석은 `블루` 또는 `레드`, 개인 분석은 `닉네임#태그`를 입력해주세요. "
                f"참가자: {names}"
            )
    checkpoint_analysis = await asyncio.wait_for(
        asyncio.to_thread(run_rofl_analysis_once, rofl.read_rofl_checkpoint_analysis_from_bytes, raw),
        timeout=75,
    )
    
    # Exact-build 16.16 cumulative combat counters live in the keyframe
    # stream. This decoder only touches keyframe chunks, so it adds little
    # overhead and fails closed on any unsupported build or validation drift.
    combat_checkpoint_analysis = None
    if rofl_combat_checkpoint is not None:
        try:
            combat_checkpoint_analysis = await asyncio.wait_for(
                asyncio.to_thread(run_rofl_analysis_once, rofl_combat_checkpoint.read_rofl_combat_checkpoints_from_bytes, raw),
                timeout=15,
            )
        except Exception as exc:
            logger.warning("ROFL combat checkpoint decode unavailable: %s", exc)
    
    target_name = normalize_rofl_match_name(resolved_riot_id) if resolved_riot_id else ""
    participants = checkpoint_analysis.get("participants", [])

    # Match-analysis UI uses Korean champion names everywhere.
    # rofl_rows were decoded with get_rofl_champion_map(), while the
    # checkpoint participant metadata may still carry English names.
    korean_champion_by_riot_id = {}
    korean_champion_by_name = {}
    for _row in rofl_rows:
        _full_name = normalize_rofl_match_name(_row.get("summoner_name"))
        _champion_name = str(_row.get("champion") or "").strip()
        if not _full_name or not _champion_name:
            continue
        korean_champion_by_riot_id[_full_name] = _champion_name
        korean_champion_by_name.setdefault(_full_name.split("#", 1)[0], _champion_name)

    for _participant in participants:
        _participant_name = normalize_rofl_match_name(_participant.get("riot_id"))
        _localized = (
            korean_champion_by_riot_id.get(_participant_name)
            or korean_champion_by_name.get(_participant_name.split("#", 1)[0])
        )
        if _localized:
            _participant["champion"] = _localized

    _limited_safe_1617 = (
        str(checkpoint_analysis.get("version") or "") == "16.17.810.4348"
        and not checkpoint_analysis.get("checkpoints")
    )

    if _team_target and _limited_safe_1617:
        return _build_1617_safe_analysis_context(
            participant=None, participants=participants, rofl_rows=rofl_rows,
            checkpoint_analysis=checkpoint_analysis, target_team=_team_target,
            normalize_rofl_match_name=normalize_rofl_match_name,
        )

    if _team_target:
        frames = sorted(
            checkpoint_analysis.get("checkpoints", []),
            key=lambda item: int(item.get("minute", 0) or 0),
        )
        usable_frames = [
            frame for frame in frames
            if isinstance(frame.get("teams"), dict)
            and _team_target in frame.get("teams", {})
            and ("red" if _team_target == "blue" else "blue") in frame.get("teams", {})
        ]
        if not usable_frames:
            raise ValueError(
                "팀 분 단위 경기 데이터를 생성하지 못했습니다. "
                "16.17 ROFL 패치 파일 3개가 모두 같은 버전인지 확인해주세요."
            )

        enemy_team = "red" if _team_target == "blue" else "blue"
        team_ko = "블루" if _team_target == "blue" else "레드"
        enemy_ko = "레드" if enemy_team == "red" else "블루"
        team_icon = "🔵" if _team_target == "blue" else "🔴"

        def _team_gap(frame):
            teams = frame.get("teams") or {}
            return int((teams.get(_team_target) or {}).get("gold", 0) or 0) - int((teams.get(enemy_team) or {}).get("gold", 0) or 0)

        def _fmt_time(ms):
            sec = max(0, int(ms or 0) // 1000)
            return f"{sec // 60}분 {sec % 60:02d}초"

        gaps = [(int(frame.get("minute", 0) or 0), _team_gap(frame), frame) for frame in usable_frames]
        peak = max(gaps, key=lambda item: item[1])
        trough = min(gaps, key=lambda item: item[1])
        final_minute, final_gap, final_frame = gaps[-1]
        reversals = []
        previous_sign = 0
        for minute, gap, _frame in gaps:
            sign = 1 if gap > 0 else -1 if gap < 0 else 0
            if sign and previous_sign and sign != previous_sign:
                reversals.append((minute, gap))
            if sign:
                previous_sign = sign

        version = str(checkpoint_analysis.get("version") or "")
        patch_label = ".".join(version.split(".")[:2]) or version or "ROFL"
        patch_display_label = patch_label
        try:
            _maj, _min = patch_label.split(".", 1)
            patch_display_label = f"{int(_maj) + 10}.{_min}" if int(_maj) < 20 else patch_label
        except Exception:
            pass

        team_color = 0x3498db if _team_target == "blue" else 0xe74c3c
        page_titles = (
            f"{team_icon} {team_ko}팀 · 경기 흐름",
            f"⚔️ {team_ko}팀 · 핵심 교전",
            f"🐉 {team_ko}팀 · 오브젝트 전환",
            f"📋 {team_ko}팀 · 총평",
        )
        pages = [discord.Embed(title=page_title, color=team_color) for page_title in page_titles]

        # Team report: interpretation first, raw logs second.
        def _nearest_frame_by_ms(time_ms):
            return min(
                usable_frames,
                key=lambda frame: abs(int(frame.get("source_time_ms", int(frame.get("minute", 0) or 0) * 60_000) or 0) - int(time_ms or 0)),
            ) if usable_frames else None

        def _frame_at_or_after_minute(minute):
            return next((frame for frame in usable_frames if int(frame.get("minute", 0) or 0) >= int(minute)), usable_frames[-1])

        def _frame_at_or_before_minute(minute):
            rows = [frame for frame in usable_frames if int(frame.get("minute", 0) or 0) <= int(minute)]
            return rows[-1] if rows else usable_frames[0]

        def _gap_text(value):
            value = int(value or 0)
            if value > 0:
                return f"+{value:,}G 우세"
            if value < 0:
                return f"{abs(value):,}G 열세"
            return "동률"

        def _compact_delta(value):
            value = int(value or 0)
            return f"{value:+,}G"

        # Locate representative early/mid snapshots without assuming that every exact minute exists.
        early_frame = min(usable_frames, key=lambda frame: abs(int(frame.get("minute", 0) or 0) - 15))
        mid_frame = min(usable_frames, key=lambda frame: abs(int(frame.get("minute", 0) or 0) - 30))
        early_minute = int(early_frame.get("minute", 0) or 0)
        mid_minute = int(mid_frame.get("minute", 0) or 0)
        early_gap = _team_gap(early_frame)
        mid_gap = _team_gap(mid_frame)

        # Minute-to-minute momentum changes. Rank by actual change in team gold gap.
        gap_changes = []
        for (prev_minute, prev_gap, prev_frame), (minute, gap, frame) in zip(gaps, gaps[1:]):
            gap_changes.append({
                "from": prev_minute,
                "to": minute,
                "before": prev_gap,
                "after": gap,
                "swing": gap - prev_gap,
                "prev_frame": prev_frame,
                "frame": frame,
            })

        meaningful_swings = sorted(
            [row for row in gap_changes if abs(int(row["swing"])) >= 900],
            key=lambda row: abs(int(row["swing"])),
            reverse=True,
        )[:3]
        meaningful_swings.sort(key=lambda row: row["from"])

        # Comeback / collapse window. The strongest narrative starts at the worst deficit
        # and ends at the first recovered lead (or the final checkpoint if no recovery).
        comeback_start = trough if trough[1] < -1000 else None
        comeback_end = None
        if comeback_start:
            comeback_end = next(
                (item for item in gaps if item[0] > comeback_start[0] and item[1] > 0),
                gaps[-1],
            )

        if final_gap > 0 and trough[1] <= -3000:
            headline = (
                f"**{trough[0]}분 {_gap_text(trough[1])}에서 뒤집어 "
                f"{final_minute}분 {_gap_text(final_gap)}로 마무리한 역전 경기.**"
            )
        elif final_gap < 0 and peak[1] >= 3000:
            headline = (
                f"**{peak[0]}분 {_gap_text(peak[1])}까지 앞섰지만 "
                f"마지막에는 {_gap_text(final_gap)}로 뒤집힌 경기.**"
            )
        elif final_gap > 0:
            headline = f"**큰 역전 없이 우세를 유지해 {_gap_text(final_gap)}로 마무리한 경기.**"
        else:
            headline = f"**중후반 주도권을 되찾지 못하고 {_gap_text(final_gap)}로 끝난 경기.**"

        # Page 1: concise game story.
        pages[0].description = f"{team_icon} **{team_ko}팀 경기 흐름**\n{headline}"
        pages[0].add_field(
            name="🧭 한눈에 보기",
            value=(
                f"`{early_minute}분` {_gap_text(early_gap)}  →  "
                f"`{mid_minute}분` {_gap_text(mid_gap)}  →  "
                f"`{final_minute}분` {_gap_text(final_gap)}\n"
                f"최대 열세 **{trough[0]}분 {_gap_text(trough[1])}** · "
                f"최대 우세 **{peak[0]}분 {_gap_text(peak[1])}**"
            ),
            inline=False,
        )
        turning_lines = []
        if comeback_start and comeback_end and comeback_end[0] > comeback_start[0]:
            turning_lines.append(
                f"🔄 **핵심 회복 구간** · {comeback_start[0]}→{comeback_end[0]}분  "
                f"`{_compact_delta(comeback_start[1])} → {_compact_delta(comeback_end[1])}`"
            )
        for row in meaningful_swings:
            direction = "📈" if row["swing"] > 0 else "📉"
            label = "주도권 상승" if row["swing"] > 0 else "주도권 하락"
            turning_lines.append(
                f"{direction} **{row['from']}→{row['to']}분 {label}** · "
                f"골드격차 `{_compact_delta(row['before'])} → {_compact_delta(row['after'])}`"
            )
        pages[0].add_field(
            name="🎯 승부가 움직인 구간",
            value="\n".join(turning_lines[:4]) if turning_lines else "큰 폭의 골드 주도권 변화가 없었습니다.",
            inline=False,
        )

        # Page 2: group individual kill packets into real fight windows.
        pid_team = {int(p.get("participant_id",0)): str(p.get("team") or "") for p in participants}
        kills = sorted(list(checkpoint_analysis.get("kills") or []), key=lambda e: int(e.get("time_ms", 0) or 0))
        own_kills = [e for e in kills if pid_team.get(int(e.get("killer_id",0) or 0)) == _team_target]
        own_deaths = [e for e in kills if pid_team.get(int(e.get("victim_id",0) or 0)) == _team_target]

        fight_groups = []
        for event in kills:
            time_ms = int(event.get("time_ms", 0) or 0)
            if not fight_groups or time_ms - fight_groups[-1][-1]["time_ms"] > 20_000:
                fight_groups.append([])
            fight_groups[-1].append({**event, "time_ms": time_ms})

        fights = []
        for group in fight_groups:
            own = sum(1 for e in group if pid_team.get(int(e.get("killer_id",0) or 0)) == _team_target)
            deaths = sum(1 for e in group if pid_team.get(int(e.get("victim_id",0) or 0)) == _team_target)
            if own + deaths < 2:
                continue
            start_ms, end_ms = group[0]["time_ms"], group[-1]["time_ms"]
            if own > deaths:
                result = "승리"
            elif own < deaths:
                result = "패배"
            else:
                result = "교환"
            before = _nearest_frame_by_ms(max(0, start_ms - 45_000))
            after = _nearest_frame_by_ms(end_ms + 45_000)
            gap_before = _team_gap(before) if before else 0
            gap_after = _team_gap(after) if after else gap_before
            fights.append({
                "start_ms": start_ms, "end_ms": end_ms,
                "kills": own, "deaths": deaths, "result": result,
                "gap_before": gap_before, "gap_after": gap_after,
                "swing": gap_after - gap_before,
            })

        fight_wins = sum(1 for row in fights if row["result"] == "승리")
        fight_losses = sum(1 for row in fights if row["result"] == "패배")
        pages[1].description = (
            f"{team_icon} **{team_ko}팀 교전 요약**\n"
            f"전체 K-D **{len(own_kills)}-{len(own_deaths)}** · 의미 있는 교전 **{fight_wins}승 {fight_losses}패**"
        )
        impactful_fights = sorted(
            fights,
            key=lambda row: (abs(int(row["kills"] - row["deaths"])), abs(int(row["swing"]))),
            reverse=True,
        )[:5]
        impactful_fights.sort(key=lambda row: row["start_ms"])
        fight_lines = []
        for row in impactful_fights:
            icon = "✅" if row["result"] == "승리" else "❌" if row["result"] == "패배" else "➖"
            time_text = _fmt_time(row["start_ms"])
            if row["end_ms"] - row["start_ms"] >= 5_000:
                time_text += f"~{_fmt_time(row['end_ms'])}"
            swing_text = ""
            if abs(int(row["swing"])) >= 500:
                swing_text = f" · 전후 골드격차 `{_compact_delta(row['gap_before'])}→{_compact_delta(row['gap_after'])}`"
            fight_lines.append(
                f"{icon} **{time_text} · {row['kills']}:{row['deaths']} {row['result']}**{swing_text}"
            )
        pages[1].add_field(
            name="⚔️ 핵심 교전",
            value="\n".join(fight_lines) if fight_lines else "여러 킬이 묶인 대규모 교전이 거의 없었습니다.",
            inline=False,
        )

        # Page 3: objectives with the measurable two-minute aftermath.
        objectives = sorted(
            [e for e in (checkpoint_analysis.get("objectives") or []) if str(e.get("team") or "") == _team_target],
            key=lambda e: int(e.get("time_ms", 0) or 0),
        )
        towers = sorted(
            [e for e in (checkpoint_analysis.get("towers") or []) if str(e.get("team") or "") == _team_target],
            key=lambda e: int(e.get("time_ms", 0) or 0),
        )
        obj_names = {"DRAGON":"드래곤", "BARON":"바론", "RIFT_HERALD":"전령"}
        objective_rows = []
        for e in objectives:
            time_ms = int(e.get("time_ms", 0) or 0)
            minute = max(0, time_ms // 60_000)
            before = _frame_at_or_before_minute(minute)
            after = _frame_at_or_after_minute(minute + 2)
            before_gap = _team_gap(before)
            after_gap = _team_gap(after)
            gained_towers = sum(1 for tower in towers if time_ms <= int(tower.get("time_ms",0) or 0) <= time_ms + 120_000)
            effect_bits = []
            gap_swing = after_gap - before_gap
            if abs(gap_swing) >= 500:
                effect_bits.append(f"2분 골드격차 `{gap_swing:+,}G`")
            if gained_towers:
                effect_bits.append(f"포탑 **{gained_towers}개**")
            effect = " · ".join(effect_bits) if effect_bits else "즉시 큰 전환 없음"
            nearby = [
                fight for fight in fights
                if int(fight.get("start_ms", 0) or 0) <= time_ms + 25_000
                and int(fight.get("end_ms", fight.get("start_ms", 0)) or 0) >= time_ms - 45_000
            ]
            fight_note = ""
            if nearby:
                fight = min(nearby, key=lambda row: abs(int(row.get("start_ms", 0) or 0) - time_ms))
                fight_note = f" · 교전 **{fight['kills']}:{fight['deaths']} {fight['result']}**"
            objective_name = obj_names.get(str(e.get('objective') or ''), '오브젝트')
            prefix = "전령 획득" if str(e.get('objective') or '') == "RIFT_HERALD" else f"{objective_name} 획득"
            objective_rows.append(
                f"• **{_fmt_time(time_ms)} {prefix}**{fight_note} → {effect}"
            )

        pages[2].description = f"{team_icon} **{team_ko}팀 오브젝트 전환력**"
        pages[2].add_field(
            name="🐉 오브젝트 전후 결과",
            value="\n".join(objective_rows[-6:]) if objective_rows else "확인된 주요 오브젝트 획득이 없습니다.",
            inline=False,
        )
        if towers:
            first_tower = towers[0]
            pages[2].add_field(
                name="🏰 구조물",
                value=f"포탑 **{len(towers)}개** 파괴 · 첫 파괴 **{_fmt_time(first_tower.get('time_ms'))}**",
                inline=False,
            )

        # Page 4: actual conclusions, not a dump of final stats.
        selected_players = [row for row in (final_frame.get("players") or []) if str(row.get("team") or "") == _team_target]
        selected_players.sort(key=lambda row: float(row.get("checkpoint_score",0) or 0), reverse=True)
        team_won = any(bool(row.get("win")) for row in rofl_rows if str(row.get("team") or "") in ("100" if _team_target == "blue" else "200", _team_target))

        # Find contributors during the decisive recovery/closing window.
        contribution_lines = []
        if comeback_start:
            start_frame = comeback_start[2]
            end_frame = comeback_end[2] if comeback_end else final_frame
        else:
            start_frame = _frame_at_or_before_minute(max(0, final_minute - 10))
            end_frame = final_frame
        start_players = {int(row.get("participant_id",0)): row for row in (start_frame.get("players") or [])}
        end_players = {int(row.get("participant_id",0)): row for row in (end_frame.get("players") or [])}
        contributions = []
        for p in participants:
            if str(p.get("team") or "") != _team_target:
                continue
            pid = int(p.get("participant_id",0) or 0)
            a, b = start_players.get(pid), end_players.get(pid)
            if not a or not b:
                continue
            gold_gain = int(b.get("total_gold",0) or 0) - int(a.get("total_gold",0) or 0)
            k = int(b.get("kills",0) or 0) - int(a.get("kills",0) or 0)
            d = int(b.get("deaths",0) or 0) - int(a.get("deaths",0) or 0)
            ass = int(b.get("assists",0) or 0) - int(a.get("assists",0) or 0)
            impact = gold_gain + (k * 350) + (ass * 140) - (d * 220)
            contributions.append((impact, p, gold_gain, k, d, ass))
        contributions.sort(reverse=True, key=lambda item: item[0])
        for _impact, p, gold_gain, k, d, ass in contributions[:2]:
            contribution_lines.append(
                f"• **{p.get('role','미지정')} · {p.get('riot_id','?')}** · "
                f"해당 구간 `{k}/{d}/{ass}` · 골드 `+{gold_gain:,}G`"
            )

        strengths = []
        issues = []
        if trough[1] <= -4000 and final_gap > 0:
            strengths.append(f"**역전력** · {trough[0]}분 {abs(trough[1]):,}G 열세를 뒤집음")
        if fight_wins > fight_losses:
            strengths.append(f"**교전 마무리** · 주요 교전 {fight_wins}승 {fight_losses}패")
        barons = [e for e in objectives if str(e.get("objective") or "") == "BARON"]
        if barons:
            strengths.append(f"**바론 전환** · {', '.join(_fmt_time(e.get('time_ms')) for e in barons[-2:])}")
        if mid_gap <= -3000:
            issues.append(f"**중반 운영** · {mid_minute}분 기준 {abs(mid_gap):,}G 열세")
        if trough[1] <= -6000:
            issues.append(f"**주도권 손실 폭** · 최대 {abs(trough[1]):,}G까지 벌어짐")
        if fight_losses >= fight_wins and fight_losses:
            issues.append(f"**교전 안정성** · 주요 교전 {fight_wins}승 {fight_losses}패")
        if not strengths:
            strengths.append("**마무리** · 마지막 체크포인트까지 경기 계획을 유지")
        if not issues:
            issues.append("**큰 구조적 약점 없음** · 세부 구간은 교전 탭에서 확인")

        if final_gap > 0 and trough[1] < 0:
            final_story = f"{trough[0]}분 {_gap_text(trough[1])} → 최종 {_gap_text(final_gap)}"
        else:
            final_story = f"최종 {_gap_text(final_gap)}"
        pages[3].description = f"{team_icon} **{team_ko}팀 총평** · {'승리' if team_won else '패배'}\n**{final_story}**"
        pages[3].add_field(name="✅ 잘한 점", value="\n".join(f"• {x}" for x in strengths[:3]), inline=False)
        pages[3].add_field(name="⚠️ 개선 포인트", value="\n".join(f"• {x}" for x in issues[:2]), inline=False)
        pages[3].add_field(
            name="⭐ 결정 구간 핵심 선수",
            value="\n".join(contribution_lines) if contribution_lines else "결정 구간 선수 데이터를 묶지 못했습니다.",
            inline=False,
        )
        labels = ("📈 경기 흐름", "⚔️ 교전", "🐉 오브젝트", "📋 총정리")
        return MatchAnalysisContext(
            guild=getattr(interaction, "guild", None),
            gid=str(getattr(interaction, "guild_id", "") or ""),
            player_name=f"{team_ko}팀",
            role="팀",
            target_team=_team_target,
            enemy_team=enemy_team,
            rofl_rows=rofl_rows,
            checkpoint_analysis=checkpoint_analysis,
            pages=pages,
            page_labels=labels,
            patch_label=patch_label,
            patch_display_label=patch_display_label,
        )

    participant = next(
        (row for row in participants if normalize_rofl_match_name(row.get("riot_id")) == target_name),
        None,
    )
    if participant is None:
        candidates = [
            row for row in participants
            if normalize_rofl_match_name(row.get("riot_id")).split("#", 1)[0] == target_name.split("#", 1)[0]
        ]
        participant = candidates[0] if len(candidates) == 1 else None
    
    if not participant:
        names = ", ".join(str(row.get("riot_id") or "?") for row in participants)
        raise ValueError(f"분석할 참가자를 찾지 못했습니다. 참가자: {names}")

    if _limited_safe_1617:
        return _build_1617_safe_analysis_context(
            participant=participant, participants=participants, rofl_rows=rofl_rows,
            checkpoint_analysis=checkpoint_analysis, resolved_riot_id=resolved_riot_id,
            normalize_rofl_match_name=normalize_rofl_match_name,
        )
    
    participant_id = int(participant["participant_id"])
    target_team = str(participant.get("team") or "")
    enemy_team = "red" if target_team == "blue" else "blue"
    
    combat_series_by_pid = {}
    if isinstance(combat_checkpoint_analysis, dict):
        for combat_row in combat_checkpoint_analysis.get("checkpoints", []):
            combat_pid = int(combat_row.get("participant_id", 0) or 0)
            if combat_pid:
                combat_series_by_pid.setdefault(combat_pid, []).append(combat_row)
        for combat_pid in list(combat_series_by_pid):
            combat_series_by_pid[combat_pid].sort(key=lambda row: int(row.get("time_ms", 0) or 0))
    combat_metric_series = combat_series_by_pid.get(participant_id, [])
    
    def combat_window_delta_for_pid(target_pid, start_ms, end_ms):
        metric_series = combat_series_by_pid.get(int(target_pid), [])
        if len(metric_series) < 2:
            return None
    
        start_ms = int(start_ms or 0)
        end_ms = int(end_ms or 0)
        timed_rows = [
            (int(row.get("time_ms", 0) or 0), row)
            for row in metric_series
        ]
        timed_rows.sort(key=lambda item: item[0])
    
        # First choice: checkpoints that fully bracket the detected fight.
        # The decoder is roughly 1-minute cadence, so a connected fight that
        # crosses a minute boundary can legitimately need close to 3 minutes
        # between the surrounding checkpoints. 125s was too strict and could
        # turn real fights into a false "no measurable fight" result.
        before_candidates = [item for item in timed_rows if item[0] <= start_ms]
        after_candidates = [item for item in timed_rows if item[0] >= end_ms]
        pair = None
        if before_candidates and after_candidates:
            candidate = (before_candidates[-1], after_candidates[0])
            if 0 < candidate[1][0] - candidate[0][0] <= 185_000:
                pair = candidate
    
        # Fallback: allow a small edge tolerance when the kill-event clock
        # and cumulative keyframe clock land on opposite sides of a minute
        # boundary. The chosen pair must still overlap nearly all of the
        # fight and stay narrow enough to be useful as a coaching interval.
        if pair is None:
            tolerance_ms = 35_000
            candidates = []
            for before_item in timed_rows:
                before_ms = before_item[0]
                if before_ms > start_ms + tolerance_ms:
                    break
                for after_item in timed_rows:
                    after_ms = after_item[0]
                    if after_ms < end_ms - tolerance_ms or after_ms <= before_ms:
                        continue
                    span = after_ms - before_ms
                    if span > 185_000:
                        continue
                    edge_error = abs(before_ms - start_ms) + abs(after_ms - end_ms)
                    candidates.append((span, edge_error, before_item, after_item))
            if candidates:
                candidates.sort(key=lambda item: (item[0], item[1]))
                _span, _edge_error, before_item, after_item = candidates[0]
                pair = (before_item, after_item)
    
        if pair is None:
            return None
    
        (before_ms, before), (after_ms, after) = pair
        keys = (
            "damage_to_champions",
            "damage_taken_from_champions",
            "cc_to_champions",
            "heal_on_teammates",
            "damage_shielded_on_teammates",
        )
        delta = {
            key: max(0.0, float(after.get(key, 0) or 0) - float(before.get(key, 0) or 0))
            for key in keys
        }
        delta.update({
            "start_ms": before_ms,
            "end_ms": after_ms,
            "duration_ms": after_ms - before_ms,
        })
        return delta
    
    def combat_window_delta(start_ms, end_ms):
        """Return factual cumulative-counter delta bracketing a fight.
    
        These are checkpoint-window totals, not event-exact fight totals.
        The window is only surfaced when it is narrow enough to remain
        useful for coaching (<= 125 seconds).
        """
        return combat_window_delta_for_pid(participant_id, start_ms, end_ms)
    
    # ------------------------------------------------------------
    # Exact-build tactical events: role quest + tower timeline.
    # These are decoded from ROFL bytes only and fail closed when the
    # checkpoint decoder does not support the uploaded build.
    # ------------------------------------------------------------
    quest_events = checkpoint_analysis.get("quests") or []
    tower_events = checkpoint_analysis.get("towers") or []
    azir_tower_events = checkpoint_analysis.get("azir_towers") or []

    quest_by_pid = {
        int(event.get("participant_id", 0) or 0): event
        for event in quest_events
        if int(event.get("participant_id", 0) or 0)
    }

    def quest_time_ms(pid):
        event = quest_by_pid.get(int(pid or 0))
        return int((event or {}).get("time_ms", 0) or 0)

    def quest_compare_text():
        mine = quest_time_ms(participant_id)
        theirs = quest_time_ms(opponent_id) if opponent_id else 0
        if not mine:
            return "퀘스트 완료 시간을 복원하지 못했습니다."
        line = f"내 완료 **{format_game_time(mine)}**"
        if theirs:
            diff_ms = mine - theirs
            if diff_ms < 0:
                line += f" · 상대 **{format_game_time(theirs)}** · **{abs(diff_ms)//1000}초 빠름**"
            elif diff_ms > 0:
                line += f" · 상대 **{format_game_time(theirs)}** · **{diff_ms//1000}초 늦음**"
            else:
                line += f" · 상대 **{format_game_time(theirs)}** · 동일"
        return line

    lane_code_by_role = {"탑": "TOP", "미드": "MID", "원딜": "BOT", "서폿": "BOT"}

    def participant_label(pid):
        pid = int(pid or 0)
        if not pid:
            return "미니언/비플레이어"
        actor = next(
            (row for row in participants if int(row.get("participant_id", 0) or 0) == pid),
            None,
        )
        if not actor:
            return "챔피언 미확인"
        actor_champion = str(actor.get("champion") or "").strip()
        return f"({actor_champion})" if actor_champion else "챔피언 미확인"

    def tower_event_line(event, *, show_lane=True):
        lane_name = {"TOP": "탑", "MID": "미드", "BOT": "바텀", "NEXUS": "넥서스"}.get(
            str(event.get("lane") or ""), str(event.get("lane") or "?")
        )
        tower_type = str(event.get("tower_type") or "")
        tower_name = {
            "OUTER_TURRET": "1차",
            "INNER_TURRET": "2차",
            "BASE_TURRET": "3차",
            "NEXUS_TURRET": "넥서스 포탑",
        }.get(tower_type, tower_type or "포탑")
        destroyed_team = "우리" if str(event.get("tower_team")) == target_team else "상대"
        attacker = "우리팀" if str(event.get("team")) == target_team else "상대팀"
        killer = participant_label(event.get("killer_id"))
        assists = [participant_label(pid) for pid in event.get("assist_ids", [])]
        involved = participant_id in [int(pid) for pid in event.get("takedown_ids", [])]
        head = f"• **{format_game_time(event.get('time_ms', 0))}** · "
        if show_lane:
            head += f"{lane_name} "
        head += f"{tower_name} · **{destroyed_team} 포탑 파괴** ({attacker})"
        detail = f"\n└ 막타 `{killer}`"
        if assists:
            detail += " · 관여 `" + ", ".join(assists) + "`"
        if involved:
            detail += " · **본인 관여**"
        return head + detail

    def add_lane_tactical_field(embed, lane_code):
        embed.add_field(name="🎯 퀘스트 완료", value=quest_compare_text(), inline=False)
        lane_towers = [
            event for event in tower_events
            if str(event.get("lane") or "") == lane_code
            and str(event.get("tower_type") or "") == "OUTER_TURRET"
        ]
        lane_towers.sort(key=lambda event: int(event.get("time_ms", 0) or 0))
        if lane_towers:
            embed.add_field(
                name="🏰 1차 타워 타이밍",
                value="\n".join(tower_event_line(event) for event in lane_towers[:2]),
                inline=False,
            )

    def add_tower_timeline(embed, *, limit=6, only_team=None):
        rows = [
            event for event in tower_events
            if only_team is None or str(event.get("team") or "") == str(only_team)
        ]
        if not rows:
            return
        embed.add_field(
            name="🏰 타워 전환",
            value="\n\n".join(tower_event_line(event) for event in rows[:limit]),
            inline=False,
        )

    # Final statsJson row is only used as an end-of-game reference.
    final_row = next(
        (
            row for row in rofl_rows
            if normalize_rofl_match_name(row.get("summoner_name")) == normalize_rofl_match_name(participant.get("riot_id"))
        ),
        None,
    )
    if not final_row:
        final_row = next(
            (
                row for row in rofl_rows
                if normalize_rofl_match_name(row.get("summoner_name")).split("#", 1)[0]
                == normalize_rofl_match_name(participant.get("riot_id")).split("#", 1)[0]
            ),
            None,
        )
    
    frames = sorted(
        checkpoint_analysis.get("checkpoints", []),
        key=lambda item: int(item.get("minute", 0)),
    )
    
    player_series = []
    opponent_id = None
    for frame in frames:
        row = next(
            (
                item for item in frame.get("players", [])
                if int(item.get("participant_id", 0)) == participant_id
            ),
            None,
        )
        if not row:
            continue
        if opponent_id is None and row.get("opponent_id"):
            opponent_id = int(row["opponent_id"])
        opp = next(
            (
                item for item in frame.get("players", [])
                if opponent_id and int(item.get("participant_id", 0)) == opponent_id
            ),
            None,
        )
        player_series.append({
            "minute": int(frame.get("minute", 0)),
            "source_time_ms": int(frame.get("source_time_ms", 0)),
            "row": row,
            "opp": opp,
            "teams": frame.get("teams") or {},
        })
    
    if not player_series:
        raise ValueError("분 단위 경기 데이터를 생성하지 못했습니다.")
    
    opponent_identity = next(
        (
            row for row in participants
            if opponent_id and int(row.get("participant_id", 0)) == int(opponent_id)
        ),
        None,
    )
    
    def signed(value, suffix=""):
        value = float(value)
        if abs(value - round(value)) < 1e-9:
            return f"{int(round(value)):+,}{suffix}"
        return f"{value:+.1f}{suffix}"
    
    # Summoner's Rift champion cumulative XP thresholds. The decoded ROFL
    # checkpoint XP has been cross-checked against final LEVEL in the same
    # replay, so user-facing analysis can show levels instead of raw XP.
    level_xp_thresholds = (
        0, 280, 660, 1140, 1720, 2400, 3180, 4060, 5040,
        6120, 7300, 8580, 9960, 11440, 13020, 14700, 16480, 18360,
        20340, 22420,
    )
    
    def level_from_xp(xp):
        value = max(0, int(xp or 0))
        level = 1
        for index, threshold in enumerate(level_xp_thresholds, start=1):
            if value >= threshold:
                level = index
            else:
                break
        return min(20 if str(role) == "탑" else 18, level)
    
    def format_game_time(time_ms):
        total_seconds = max(0, int(time_ms or 0) // 1000)
        minute, second = divmod(total_seconds, 60)
        return f"{minute}분 {second:02d}초"
    
    def gold_swing_text(delta):
        delta = int(delta or 0)
        if delta > 0:
            return f"{delta:,}G 이득"
        if delta < 0:
            return f"{abs(delta):,}G 손해"
        return "변화 없음"
    
    def gold_lead_text(delta, team=False):
        delta = int(delta or 0)
        subject = "우리 팀" if team else "내가"
        if delta > 0:
            return f"{subject} {delta:,}G 앞섬"
        if delta < 0:
            return f"{subject} {abs(delta):,}G 뒤처짐"
        return f"{subject} 골드 동률"
    
    def nearest_series_by_ms(time_ms):
        return min(
            player_series,
            key=lambda item: abs(int(item["source_time_ms"]) - int(time_ms)),
        )
    
    def series_before_ms(time_ms):
        candidates = [
            item for item in player_series
            if int(item.get("source_time_ms", 0) or 0) <= int(time_ms)
        ]
        return candidates[-1] if candidates else player_series[0]
    
    def series_after_ms(time_ms):
        candidates = [
            item for item in player_series
            if int(item.get("source_time_ms", 0) or 0) >= int(time_ms)
        ]
        return candidates[0] if candidates else player_series[-1]
    
    def series_at_minute(minute):
        return min(player_series, key=lambda item: abs(int(item["minute"]) - int(minute)))
    
    # ------------------------------------------------------------
    # Teamfight detector
    #
    # Do NOT classify "many kills near each other" by itself.
    # Kills are chained only when the kill-participant sets overlap,
    # proving that the same champions are participating/assisting across
    # multiple deaths. Then require a large connected fight.
    # ------------------------------------------------------------
    kill_events = sorted(
        checkpoint_analysis.get("kills", []),
        key=lambda event: int(event.get("time_ms", 0)),
    )
    
    def kill_participants(event):
        values = set()
        killer = int(event.get("killer_id", 0) or 0)
        victim = int(event.get("victim_id", 0) or 0)
        if killer:
            values.add(killer)
        if victim:
            values.add(victim)
        values.update(int(pid) for pid in event.get("assist_ids", []) if int(pid))
        return values
    
    clusters = []
    current = []
    current_people = set()
    for event in kill_events:
        people = kill_participants(event)
        if not current:
            current = [event]
            current_people = set(people)
            continue
    
        gap_ms = int(event.get("time_ms", 0)) - int(current[-1].get("time_ms", 0))
        overlap = len(current_people & people)
    
        # Shared participants/assists are mandatory. This prevents unrelated
        # simultaneous kills elsewhere on the map from becoming one fight.
        if gap_ms <= 18_000 and overlap >= 2:
            current.append(event)
            current_people.update(people)
        else:
            clusters.append((current, set(current_people)))
            current = [event]
            current_people = set(people)
    if current:
        clusters.append((current, set(current_people)))
    
    teamfights = []
    participant_team = {
        int(row["participant_id"]): str(row.get("team") or "")
        for row in participants
    }
    for events, people in clusters:
        assisted_deaths = sum(1 for event in events if event.get("assist_ids"))
        repeated_people = {}
        for event in events:
            for pid in kill_participants(event):
                repeated_people[pid] = repeated_people.get(pid, 0) + 1
    
        # A real large fight needs a same-team participation core, not merely
        # several deaths close in time. Count champions from each team that
        # appear in at least two linked kill/assist events and require 3+.
        repeated_team_core = {"blue": set(), "red": set()}
        for pid, count in repeated_people.items():
            if count < 2:
                continue
            team = participant_team.get(int(pid))
            if team in repeated_team_core:
                repeated_team_core[team].add(int(pid))
        team_core_size = max((len(value) for value in repeated_team_core.values()), default=0)
    
        # Keep the existing anti-noise gates, but make the agreed same-team
        # 3-player overlap the decisive connected-fight condition.
        if len(events) < 3 or len(people) < 5 or assisted_deaths < 2 or team_core_size < 3:
            continue
    
        start_ms = int(events[0]["time_ms"])
        end_ms = int(events[-1]["time_ms"])
        blue_kills = 0
        red_kills = 0
        for event in events:
            killer = int(event.get("killer_id", 0) or 0)
            killer_team = participant_team.get(killer)
            if killer_team == "blue":
                blue_kills += 1
            elif killer_team == "red":
                red_kills += 1
    
        own_kills = blue_kills if target_team == "blue" else red_kills
        enemy_kills = red_kills if target_team == "blue" else blue_kills
    
        target_k = sum(int(event.get("killer_id", 0) or 0) == participant_id for event in events)
        target_d = sum(int(event.get("victim_id", 0) or 0) == participant_id for event in events)
        target_a = sum(participant_id in [int(x) for x in event.get("assist_ids", [])] for event in events)
        target_involved = any(participant_id in kill_participants(event) for event in events)
    
        # Bracket the fight with factual checkpoints. Nearest ±30s could
        # select a checkpoint from the wrong side of the fight.
        before = series_before_ms(start_ms)
        after = series_after_ms(end_ms)
        score_before = float(before["row"].get("checkpoint_score") or 0)
        score_after = float(after["row"].get("checkpoint_score") or 0)
        own_before = (before["teams"].get(target_team) or {}).get("gold", 0)
        enemy_before = (before["teams"].get(enemy_team) or {}).get("gold", 0)
        own_after = (after["teams"].get(target_team) or {}).get("gold", 0)
        enemy_after = (after["teams"].get(enemy_team) or {}).get("gold", 0)
        gold_gap_before = int(own_before) - int(enemy_before)
        gold_gap_after = int(own_after) - int(enemy_after)
    
        if own_kills > enemy_kills:
            outcome = "승리"
        elif own_kills < enemy_kills:
            outcome = "패배"
        else:
            outcome = "교환"
    
        gold_gap_delta = gold_gap_after - gold_gap_before
        if gold_gap_delta >= 500:
            gold_outcome = "이득"
        elif gold_gap_delta <= -500:
            gold_outcome = "손해"
        else:
            gold_outcome = "비슷"
    
        fight_combat_window = combat_window_delta(start_ms, end_ms)
        allied_fight_people = [
            pid for pid in people if participant_team.get(int(pid)) == target_team
        ]
        allied_damage_rows = []
        for allied_pid in allied_fight_people:
            allied_window = combat_window_delta_for_pid(allied_pid, start_ms, end_ms)
            if allied_window is not None:
                allied_damage_rows.append((
                    int(allied_pid),
                    int(round(float(allied_window.get("damage_to_champions", 0) or 0))),
                ))
        allied_damage_rows.sort(key=lambda pair: pair[1], reverse=True)
        target_damage_rank = next(
            (index + 1 for index, (pid, _damage) in enumerate(allied_damage_rows) if pid == participant_id),
            None,
        )
        allied_damage_total = sum(max(0, damage) for _pid, damage in allied_damage_rows)
        target_damage_value = next((damage for pid, damage in allied_damage_rows if pid == participant_id), 0)
        target_damage_share = (target_damage_value / allied_damage_total * 100.0) if allied_damage_total > 0 else None
        blue_people_count = sum(1 for pid in people if participant_team.get(int(pid)) == "blue")
        red_people_count = sum(1 for pid in people if participant_team.get(int(pid)) == "red")
    
        teamfights.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "minute": start_ms / 60_000,
            "deaths": len(events),
            "unique_people": len(people),
            "own_kills": own_kills,
            "enemy_kills": enemy_kills,
            "outcome": outcome,
            "gold_outcome": gold_outcome,
            "target_involved": target_involved,
            "target_k": target_k,
            "target_d": target_d,
            "target_a": target_a,
            "score_delta": score_after - score_before,
            "gold_gap_before": gold_gap_before,
            "gold_gap_after": gold_gap_after,
            "gold_gap_delta": gold_gap_delta,
            "team_core_size": team_core_size,
            "combat_window": fight_combat_window,
            "target_damage_rank": target_damage_rank,
            "target_damage_rank_total": len(allied_damage_rows),
            "target_damage_share": target_damage_share,
            "blue_people_count": blue_people_count,
            "red_people_count": red_people_count,
        })
    
    patch_label = ".".join(str(checkpoint_analysis.get("version") or "").split(".")[:2]) or "16.16"
    # Replay internals expose the 2026 client line as 16.x, while the live
    # League patch label shown to players is 26.x. Keep the raw value for
    # analysis/decoder logic and translate only the user-facing label.
    patch_display_label = patch_label
    try:
        _patch_major, _patch_minor = patch_label.split(".", 1)
        _patch_major_int = int(_patch_major)
        if 10 <= _patch_major_int < 20:
            patch_display_label = f"{_patch_major_int + 10}.{_patch_minor}"
    except (TypeError, ValueError):
        patch_display_label = patch_label
    player_name = participant.get("riot_id") or resolved_riot_id
    role = participant.get("role", "미지정")
    champion = participant.get("champion", "")
    
    def interval_participation(pid, team_name, start_minute, end_minute):
        start_ms = int(float(start_minute) * 60_000)
        end_ms = int(float(end_minute) * 60_000)
        relevant = [
            event for event in kill_events
            if start_ms <= int(event.get("time_ms", 0) or 0) < end_ms
        ]
        team_kills = 0
        takedowns = 0
        deaths = 0
        pid = int(pid or 0)
        for event in relevant:
            killer = int(event.get("killer_id", 0) or 0)
            if participant_team.get(killer) == team_name:
                team_kills += 1
            if killer == pid or pid in [int(x) for x in event.get("assist_ids", [])]:
                takedowns += 1
            if int(event.get("victim_id", 0) or 0) == pid:
                deaths += 1
        rate = (takedowns / team_kills * 100.0) if team_kills else 0.0
        return {"takedowns": takedowns, "team_kills": team_kills, "rate": rate, "deaths": deaths}
    
    opponent_final_row = None
    if opponent_identity:
        opponent_full_name = normalize_rofl_match_name(opponent_identity.get("riot_id"))
        opponent_final_row = next(
            (row for row in rofl_rows if normalize_rofl_match_name(row.get("summoner_name")) == opponent_full_name),
            None,
        )
    
    def _event_actor_line(pid, event):
        """Return factual K/A participation for one participant in a kill event."""
        pid = int(pid or 0)
        killer = int(event.get("killer_id", 0) or 0)
        assists = [int(x) for x in event.get("assist_ids", []) if int(x)]
        return (1 if killer == pid else 0, 1 if pid in assists else 0)
    
    def _team_gold_gap_from_series(item, team_name):
        if not item:
            return 0
        other = "red" if team_name == "blue" else "blue"
        own_gold = int(((item.get("teams") or {}).get(team_name) or {}).get("gold", 0) or 0)
        enemy_gold = int(((item.get("teams") or {}).get(other) or {}).get("gold", 0) or 0)
        return own_gold - enemy_gold
    
    def participation_impact_windows(pid, team_name, counterpart_pid=0, start_ms=0, end_ms=None, cluster_gap_ms=35_000):
        """
        Build compact, event-led kill participation windows.
    
        This deliberately does not call a participation a roam/gank because ROFL position
        data is not decoded reliably enough yet.  Gold impact is the change in team gold
        gap between the checkpoint before the first event and checkpoint after the last.
        """
        pid = int(pid or 0)
        counterpart_pid = int(counterpart_pid or 0)
        if not pid:
            return []
        filtered = []
        for event in kill_events:
            t = int(event.get("time_ms", 0) or 0)
            if t < int(start_ms or 0):
                continue
            if end_ms is not None and t >= int(end_ms):
                continue
            k, a = _event_actor_line(pid, event)
            if k or a:
                filtered.append(event)
        if not filtered:
            return []
    
        clusters = []
        cur = [filtered[0]]
        for event in filtered[1:]:
            if int(event.get("time_ms", 0) or 0) - int(cur[-1].get("time_ms", 0) or 0) <= cluster_gap_ms:
                cur.append(event)
            else:
                clusters.append(cur)
                cur = [event]
        if cur:
            clusters.append(cur)
    
        rows = []
        for events in clusters:
            c_start = int(events[0].get("time_ms", 0) or 0)
            c_end = int(events[-1].get("time_ms", 0) or 0)
            # Include all kills in the same short scene when comparing the counterpart.
            scene_start = max(0, c_start - 12_000)
            scene_end = c_end + 12_000
            scene = [
                event for event in kill_events
                if scene_start <= int(event.get("time_ms", 0) or 0) <= scene_end
            ]
            kills = assists = 0
            for event in events:
                k, a = _event_actor_line(pid, event)
                kills += k
                assists += a
            counterpart_k = counterpart_a = 0
            if counterpart_pid:
                for event in scene:
                    k, a = _event_actor_line(counterpart_pid, event)
                    counterpart_k += k
                    counterpart_a += a
            before = series_before_ms(c_start)
            after = series_after_ms(c_end)
            before_gap = _team_gold_gap_from_series(before, team_name)
            after_gap = _team_gold_gap_from_series(after, team_name)
            personal_gap_before = 0
            personal_gap_after = 0
            if before and before.get("opp"):
                personal_gap_before = int(before["row"].get("total_gold", 0) or 0) - int(before["opp"].get("total_gold", 0) or 0)
            if after and after.get("opp"):
                personal_gap_after = int(after["row"].get("total_gold", 0) or 0) - int(after["opp"].get("total_gold", 0) or 0)
            rows.append({
                "start_ms": c_start,
                "end_ms": c_end,
                "kills": kills,
                "assists": assists,
                "takedowns": kills + assists,
                "counterpart_takedowns": counterpart_k + counterpart_a,
                "gold_gap_before": before_gap,
                "gold_gap_after": after_gap,
                "gold_gap_delta": after_gap - before_gap,
                "gold_frame_before_ms": int((before or {}).get("source_time_ms", 0) or 0),
                "gold_frame_after_ms": int((after or {}).get("source_time_ms", 0) or 0),
                "personal_gold_gap_delta": personal_gap_after - personal_gap_before,
            })
        return rows
    
    def impact_line(row, counterpart_label=None):
        kd = int(row.get("kills", 0) or 0)
        ad = int(row.get("assists", 0) or 0)
        delta = int(row.get("gold_gap_delta", 0) or 0)
        personal_delta = int(row.get("personal_gold_gap_delta", 0) or 0)
        if delta > 0:
            impact = f"팀 `+{delta:,}G`"
        elif delta < 0:
            impact = f"팀 `-{abs(delta):,}G`"
        else:
            impact = "팀 `±0G`"
        if personal_delta > 0:
            personal = f"상대와 골드격차 `+{personal_delta:,}G`"
        elif personal_delta < 0:
            personal = f"상대와 골드격차 `-{abs(personal_delta):,}G`"
        else:
            personal = "상대와 골드격차 `±0G`"
        line = f"• **{format_game_time(row['start_ms'])}** · `{kd}킬 {ad}어시` → {personal} · {impact}"
        if counterpart_label:
            line += f"\n└ {counterpart_label} 같은 장면 킬관여 `{int(row.get('counterpart_takedowns', 0) or 0)}`회"
        return line
    
    def add_impact_highlights(embed, pid, team_name, counterpart_pid=0, counterpart_label=None,
                              start_ms=0, end_ms=None, field_name="🎯 영향력 있었던 장면", limit=4):
        rows = participation_impact_windows(
            pid, team_name, counterpart_pid=counterpart_pid,
            start_ms=start_ms, end_ms=end_ms,
        )
        if not rows:
            embed.add_field(name=field_name, value="해당 구간에서 킬/어시스트 관여 기록이 없습니다.", inline=False)
            return []
        # Prefer scenes that changed the team's actual gold state, then takedown volume.
        ranked = sorted(
            rows,
            key=lambda r: (
                int(r.get("gold_gap_delta", 0) or 0) > 0,
                int(r.get("gold_gap_delta", 0) or 0),
                int(r.get("personal_gold_gap_delta", 0) or 0),
                int(r.get("takedowns", 0) or 0),
            ),
            reverse=True,
        )
        chosen = sorted(ranked[:limit], key=lambda r: int(r.get("start_ms", 0) or 0))
        embed.add_field(
            name=field_name,
            value="\n".join(impact_line(row, counterpart_label) for row in chosen),
            inline=False,
        )
        return rows
    
    # ------------------------------------------------------------
    # Page 1: early growth
    # ------------------------------------------------------------
    early = [item for item in player_series if 5 <= item["minute"] <= 15 and item["opp"]]
    early_embed = discord.Embed(
        title=f"🌱 초반 성장 - {patch_label}",
        description=f"🎮 **{player_name}**\n🏹 `{role}` · **{champion}` · 라인전 종료 전 성장 흐름",
        color=0x2ecc71,
    )
    if early:
        first, last = early[0], early[-1]
        r0, o0 = first["row"], first["opp"]
        r1, o1 = last["row"], last["opp"]
    
        swings = []
        for prev, cur in zip(early, early[1:]):
            pr, po = prev["row"], prev["opp"]
            cr, co = cur["row"], cur["opp"]
            my_gold_gain = int(cr["total_gold"]) - int(pr["total_gold"])
            opp_gold_gain = int(co["total_gold"]) - int(po["total_gold"])
            my_cs_value = int(cr["lane_cs"]) + (int(cr["jungle_cs"]) if role == "정글" else 0)
            prev_my_cs_value = int(pr["lane_cs"]) + (int(pr["jungle_cs"]) if role == "정글" else 0)
            opp_cs_value = int(co["lane_cs"]) + (int(co["jungle_cs"]) if role == "정글" else 0)
            prev_opp_cs_value = int(po["lane_cs"]) + (int(po["jungle_cs"]) if role == "정글" else 0)
            my_cs_gain = my_cs_value - prev_my_cs_value
            opp_cs_gain = opp_cs_value - prev_opp_cs_value
            my_activity = interval_participation(participant_id, target_team, prev["minute"], cur["minute"])
            opp_activity = interval_participation(opponent_id, enemy_team, prev["minute"], cur["minute"]) if opponent_id else None
            swings.append({
                "from": prev["minute"], "to": cur["minute"],
                "gold_gain": my_gold_gain, "opp_gold_gain": opp_gold_gain,
                "cs_gain": my_cs_gain, "opp_cs_gain": opp_cs_gain,
                "end_gold": int(cr["total_gold"]),
                "opp_end_gold": int(co["total_gold"]),
                "end_cs": my_cs_value,
                "opp_end_cs": opp_cs_value,
                "activity": my_activity,
                "opp_activity": opp_activity,
                "start_level": level_from_xp(pr["xp"]),
                "end_level": level_from_xp(cr["xp"]),
                "opp_start_level": level_from_xp(po["xp"]),
                "opp_end_level": level_from_xp(co["xp"]),
                "gain_diff": my_gold_gain - opp_gold_gain,
            })
        if swings:
            worst = min(swings, key=lambda item: item["gain_diff"])
            best = max(swings, key=lambda item: item["gain_diff"])
    
            def early_window_text(item):
                lines = [
                    f"**{item['from']} ~ {item['to']}분**",
                    f"└ 💰 구간 종료 골드 `{item['end_gold']:,}G` vs 상대 `{item['opp_end_gold']:,}G`",
                ]
                if role != "서폿":
                    lines.append(f"└ 🌾 총 CS `{item['end_cs']}` vs 상대 `{item['opp_end_cs']}`")
                lines.append(
                    f"└ 📈 레벨 `{item['start_level']} → {item['end_level']}` vs 상대 "
                    f"`{item['opp_start_level']} → {item['opp_end_level']}`"
                )
                if role in ("서폿", "정글"):
                    activity = item.get("activity") or {}
                    opp_activity = item.get("opp_activity") or {}
                    lines.append(
                        f"└ ⚔️ 킬관여 `{activity.get('takedowns', 0)}/{activity.get('team_kills', 0)}` "
                        f"({activity.get('rate', 0):.0f}%) vs 상대 "
                        f"`{opp_activity.get('takedowns', 0)}/{opp_activity.get('team_kills', 0)}` "
                        f"({opp_activity.get('rate', 0):.0f}%)"
                    )
                return "\n".join(lines)
    
            early_embed.add_field(
                name="📉 피드백 체크 구간",
                value=early_window_text(worst),
                inline=False,
            )
            early_embed.add_field(
                name="📈 상승 구간",
                value=early_window_text(best),
                inline=False,
            )
    else:
        early_embed.add_field(name="📌 분석", value="라인전 비교 데이터를 만들 수 없습니다.", inline=False)
    early_embed.set_footer(text="1 / 4 · 초반 성장")
    
    # ------------------------------------------------------------
    # Page 2: mid-game operation / resource acquisition
    # ------------------------------------------------------------
    mid = [item for item in player_series if item["minute"] >= 15 and item["opp"]]
    operation_embed = discord.Embed(
        title=f"🧭 중반 운영 - {patch_label}",
        description=f"🎮 **{player_name}**\n🏹 `{role}` · **{champion}` · 라인전 이후 상대와 성장 격차",
        color=0x3498db,
    )
    windows = []
    for start_minute in range(15, max((item["minute"] for item in mid), default=15), 5):
        start_item = min(mid, key=lambda item: abs(item["minute"] - start_minute)) if mid else None
        end_candidates = [item for item in mid if item["minute"] >= start_minute + 4]
        end_item = min(end_candidates, key=lambda item: abs(item["minute"] - (start_minute + 5))) if end_candidates else None
        if not start_item or not end_item or end_item["minute"] <= start_item["minute"]:
            continue
    
        mins = end_item["minute"] - start_item["minute"]
        sr, er = start_item["row"], end_item["row"]
        so, eo = start_item["opp"], end_item["opp"]
    
        lane_gain = int(er["lane_cs"]) - int(sr["lane_cs"])
        jg_gain = int(er["jungle_cs"]) - int(sr["jungle_cs"])
        opp_lane_gain = int(eo["lane_cs"]) - int(so["lane_cs"])
        opp_jg_gain = int(eo["jungle_cs"]) - int(so["jungle_cs"])
        xp_gain = int(er["xp"]) - int(sr["xp"])
        opp_xp_gain = int(eo["xp"]) - int(so["xp"])
        gold_gain = int(er["total_gold"]) - int(sr["total_gold"])
        opp_gold_gain = int(eo["total_gold"]) - int(so["total_gold"])
    
        windows.append({
            "start": start_item["minute"],
            "end": end_item["minute"],
            "start_cs": int(sr["lane_cs"]) + int(sr["jungle_cs"]),
            "end_cs": int(er["lane_cs"]) + int(er["jungle_cs"]),
            "opp_start_cs": int(so["lane_cs"]) + int(so["jungle_cs"]),
            "opp_end_cs": int(eo["lane_cs"]) + int(eo["jungle_cs"]),
            "cs_gain": lane_gain + jg_gain,
            "opp_cs_gain": opp_lane_gain + opp_jg_gain,
            "gold_gain": gold_gain,
            "opp_gold_gain": opp_gold_gain,
            "start_level": level_from_xp(sr["xp"]),
            "end_level": level_from_xp(er["xp"]),
            "opp_start_level": level_from_xp(so["xp"]),
            "opp_end_level": level_from_xp(eo["xp"]),
            # Normalized values are internal-only so windows of slightly
            # different length can still be ranked fairly.
            "cs_pm": (lane_gain + jg_gain) / mins,
            "opp_cs_pm": (opp_lane_gain + opp_jg_gain) / mins,
            "xp_pm": xp_gain / mins,
            "opp_xp_pm": opp_xp_gain / mins,
            "gold_pm": gold_gain / mins,
            "opp_gold_pm": opp_gold_gain / mins,
        })
    
    def gold_gap_state(value):
        value = int(value or 0)
        if value > 0:
            return f"골드차이 +{value:,}G"
        if value < 0:
            return f"골드차이 -{abs(value):,}G"
        return "골드차이 0G"

    def gold_gap_delta_text(before_value, after_value, *, label="골드차이"):
        before_value = int(before_value or 0)
        after_value = int(after_value or 0)
        delta = after_value - before_value

        if delta == 0:
            return f"{label} 변화 없음"
        if before_value > 0 and after_value < 0:
            return f"{label} {abs(delta):,}G 악화 · 역전당함"
        if before_value < 0 and after_value > 0:
            return f"{label} {abs(delta):,}G 개선 · 역전"
        if before_value >= 0 and after_value >= 0:
            return (
                f"{label} {abs(delta):,}G 더 벌림"
                if after_value > before_value
                else f"{label} {abs(delta):,}G 좁혀짐"
            )
        if before_value <= 0 and after_value <= 0:
            return (
                f"{label} {abs(delta):,}G 더 벌어짐"
                if abs(after_value) > abs(before_value)
                else f"{label} {abs(delta):,}G 좁혀짐"
            )
        return f"{label} {delta:+,}G"

    # Same-position opponent resolved from the checkpoint participant table.
    # Do not self-reference these locals before assignment: some role paths
    # (notably top analysis) reach this block before any role-specific alias
    # has ever been created.
    opponent_champion_name = str(
        (opponent_identity or {}).get("champion")
        or "상대 챔피언"
    ).strip() or "상대 챔피언"
    opponent_jungle_champion_name = (
        opponent_champion_name if role == "정글" else "상대 정글"
    )
    opponent_top_champion_name = (
        opponent_champion_name if role == "탑" else "상대 탑"
    )

    def raw_gold_compare_delta(before_value, after_value, opponent_label):
        delta = int(after_value or 0) - int(before_value or 0)
        return f"vs `{opponent_label}` 골드차이 `{delta:+,}G`"

    def gold_swing_text(value):
        value = int(value or 0)
        if value > 0:
            return f"골드차이 +{value:,}G"
        if value < 0:
            return f"골드차이 -{abs(value):,}G"
        return "골드차이 0G"
    
    if role == "서폿":
        operation_embed.title = f"🧭 서포터 운영 - {patch_label}"
        operation_embed.description = f"🎮 **{player_name}**\n🏹 `{role}` · **{champion}` · 시야와 합류 중심"
        rs = (final_row or {}).get("rofl_stats") or {}
        ors = (opponent_final_row or {}).get("rofl_stats") or {}
        vision_rows = [
            ("👁️ 시야 점수", "VISION_SCORE"),
            ("🟢 와드 설치", "WARD_PLACED"),
            ("🧹 와드 제거", "WARD_KILLED"),
            ("🟥 제어 와드 구매", "VISION_WARDS_BOUGHT_IN_GAME"),
        ]
        vision_lines = []
        for label, key in vision_rows:
            mine = int(float(rs.get(key, 0) or 0))
            theirs = int(float(ors.get(key, 0) or 0)) if opponent_final_row else None
            if theirs is None:
                vision_lines.append(f"{label} `{mine}`")
            else:
                vision_lines.append(f"{label} `{mine}` vs 상대 `{theirs}`")
        operation_embed.add_field(
            name="👁️ 경기 시야 활동",
            value="\n".join(vision_lines),
            inline=False,
        )
        if mid:
            support_start = mid[0]["minute"]
            support_end = mid[-1]["minute"] + 1
            mine = interval_participation(participant_id, target_team, support_start, support_end)
            theirs = interval_participation(opponent_id, enemy_team, support_start, support_end) if opponent_id else {}
            operation_embed.add_field(
                name="🤝 라인전 이후 교전 합류",
                value=(
                    f"**{support_start}분 이후**\n"
                    f"⚔️ 킬관여 `{mine.get('takedowns', 0)}/{mine.get('team_kills', 0)}` "
                    f"({mine.get('rate', 0):.0f}%) vs 상대 "
                    f"`{theirs.get('takedowns', 0)}/{theirs.get('team_kills', 0)}` "
                    f"({theirs.get('rate', 0):.0f}%)\n"
                    f"💀 사망 `{mine.get('deaths', 0)}`회 vs 상대 `{theirs.get('deaths', 0)}`회"
                ),
                inline=False,
            )
    elif windows:
        for item in windows:
            start_gap = (
                int(next(x for x in mid if x["minute"] == item["start"])["row"]["total_gold"])
                - int(next(x for x in mid if x["minute"] == item["start"])["opp"]["total_gold"])
            )
            end_gap = (
                int(next(x for x in mid if x["minute"] == item["end"])["row"]["total_gold"])
                - int(next(x for x in mid if x["minute"] == item["end"])["opp"]["total_gold"])
            )
            item["start_gold_gap"] = start_gap
            item["end_gold_gap"] = end_gap
            item["gold_gap_change"] = end_gap - start_gap
    
        weakest = min(windows, key=lambda item: item["gold_gap_change"])
        strongest = max(windows, key=lambda item: item["gold_gap_change"])
    
        def operation_window_text(item):
            change = int(item["gold_gap_change"])
            change_text = f"+{change:,}G 개선" if change > 0 else f"{abs(change):,}G 악화" if change < 0 else "변화 없음"
            return (
                f"**{item['start']} ~ {item['end']}분**\n"
                f"└ 💰 {gold_gap_delta_text(item['start_gold_gap'], item['end_gold_gap'])}\n"
                f"└ 🌾 CS `{item['start_cs']} → {item['end_cs']}` (+{item['cs_gain']}) "
                f"vs 상대 `{item['opp_start_cs']} → {item['opp_end_cs']}` (+{item['opp_cs_gain']})\n"
                f"└ ⬆️ 레벨 `{item['start_level']} → {item['end_level']}` vs 상대 "
                f"`{item['opp_start_level']} → {item['opp_end_level']}`"
            )
    
        operation_embed.add_field(
            name="🔻 상대에게 가장 많이 벌어진 구간",
            value=operation_window_text(weakest),
            inline=False,
        )
        operation_embed.add_field(
            name="🔺 상대와 격차를 가장 많이 만든/좁힌 구간",
            value=operation_window_text(strongest),
            inline=False,
        )
    
        overall_start = mid[0]
        overall_end = mid[-1]
        rr0, rr1 = overall_start["row"], overall_end["row"]
        oo0, oo1 = overall_start["opp"], overall_end["opp"]
        my_cs_start = int(rr0["lane_cs"]) + int(rr0["jungle_cs"])
        my_cs_end = int(rr1["lane_cs"]) + int(rr1["jungle_cs"])
        opp_cs_start = int(oo0["lane_cs"]) + int(oo0["jungle_cs"])
        opp_cs_end = int(oo1["lane_cs"]) + int(oo1["jungle_cs"])
        my_cs_gain = my_cs_end - my_cs_start
        opp_cs_gain = opp_cs_end - opp_cs_start
        start_gold_gap = int(rr0["total_gold"]) - int(oo0["total_gold"])
        end_gold_gap = int(rr1["total_gold"]) - int(oo1["total_gold"])
        operation_embed.add_field(
            name="📦 라인전 이후 전체 성장",
            value=(
                f"**{overall_start['minute']} ~ {overall_end['minute']}분**\n"
                f"💰 골드 차이 {gold_gap_delta_text(start_gold_gap, end_gold_gap)}\n"
                f"🌾 CS `{my_cs_start} → {my_cs_end}` (+{my_cs_gain}) "
                f"vs 상대 `{opp_cs_start} → {opp_cs_end}` (+{opp_cs_gain})\n"
                f"⬆️ 레벨 `{level_from_xp(rr0['xp'])} → {level_from_xp(rr1['xp'])}` vs 상대 "
                f"`{level_from_xp(oo0['xp'])} → {level_from_xp(oo1['xp'])}`"
            ),
            inline=False,
        )
    else:
        operation_embed.add_field(name="📌 분석", value="라인전 이후 비교 구간이 부족합니다.", inline=False)
    operation_embed.set_footer(text="2 / 4 · 중반 운영")
    
    # ------------------------------------------------------------
    # Page 3: connected 3+ player fight analysis
    # ------------------------------------------------------------
    combat_embed = discord.Embed(
        title=f"⚔️ 교전 능력 - {patch_label}",
        description=f"🎮 **{player_name}**\n🏹 `{role}` · **{champion}`",
        color=0xe67e22,
    )
    
    involved_fights = [fight for fight in teamfights if fight["target_involved"]]
    uninvolved_fights = [fight for fight in teamfights if not fight["target_involved"]]
    if involved_fights:
        fight_lines = []
        for fight in involved_fights[:5]:
            icon = "🔵" if fight["outcome"] == "승리" else "🔴" if fight["outcome"] == "패배" else "⚪"
            detail = (
                f"{icon} **{format_game_time(fight['start_ms'])} · 전투 {fight['outcome']} "
                f"({fight['own_kills']}:{fight['enemy_kills']})**\n"
                f"└ 💰 팀 골드 `{gold_swing_text(fight['gold_gap_delta'])}`\n"
                f"└ 본인 `{fight['target_k']}/{fight['target_d']}/{fight['target_a']}`"
            )
            combat_window = fight.get("combat_window")
            if combat_window:
                dealt = int(round(float(combat_window.get("damage_to_champions", 0) or 0)))
                taken = int(round(float(combat_window.get("damage_taken_from_champions", 0) or 0)))
                detail += (
                    f"\n└ 📐 측정구간 `{format_game_time(combat_window['start_ms'])}~{format_game_time(combat_window['end_ms'])}` · "
                    f"챔피언딜 `{dealt:,}` · 받은딜 `{taken:,}`"
                )
                damage_rank = fight.get("target_damage_rank")
                damage_rank_total = int(fight.get("target_damage_rank_total", 0) or 0)
                if damage_rank and damage_rank_total >= 2:
                    detail += f" · 아군 교전딜 `{damage_rank}/{damage_rank_total}위`"
            fight_lines.append(detail)
        combat_embed.add_field(
            name="🔥 3인 이상 교전",
            value="\n\n".join(fight_lines),
            inline=False,
        )
        wins = sum(fight["outcome"] == "승리" for fight in involved_fights)
        losses = sum(fight["outcome"] == "패배" for fight in involved_fights)
        deaths = sum(fight["target_d"] for fight in involved_fights)
        takedowns = sum(fight["target_k"] + fight["target_a"] for fight in involved_fights)
        no_takedown_deaths = sum(
            1 for fight in involved_fights
            if fight["target_d"] > 0 and (fight["target_k"] + fight["target_a"]) == 0
        )
        combat_embed.add_field(
            name="📊 교전 요약",
            value=(
                f"참여 교전 `{len(involved_fights)}`회 · 팀 `{wins}승 {losses}패`\n"
                f"본인 킬관여 `{takedowns}`회 · 교전 사망 `{deaths}`회\n"
                f"킬/어시스트 없이 끝난 사망 교전 `{no_takedown_deaths}`회"
            ),
            inline=False,
        )
    else:
        combat_embed.add_field(
            name="🔥 3인 이상 교전",
            value="3인 이상 교전에 직접 참여한 기록이 없습니다.",
            inline=False,
        )
    
    if uninvolved_fights:
        lines = []
        for fight in uninvolved_fights[:5]:
            lines.append(
                f"• **{format_game_time(fight['start_ms'])}** · 팀 전투 `{fight['outcome']}` "
                f"({fight['own_kills']}:{fight['enemy_kills']}) · 팀 골드 `{gold_swing_text(fight['gold_gap_delta'])}`"
            )
        combat_embed.add_field(
            name="👀 내가 참여하지 않은 교전",
            value="\n".join(lines),
            inline=False,
        )
    
    if final_row:
        rs = final_row.get("rofl_stats") or {}
        damage = int(final_row.get("damage_to_champions", 0) or 0)
        taken = int(rs.get("TOTAL_DAMAGE_TAKEN_FROM_CHAMPIONS", 0) or 0)
        lines = [f"💥 챔피언에게 가한 피해 `{damage:,}`"]
        if taken:
            lines.append(f"🛡️ 챔피언에게 받은 피해 `{taken:,}`")
        combat_embed.add_field(
            name="🏁 경기 전체 교전 지표",
            value="\n".join(lines),
            inline=False,
        )
    combat_embed.set_footer(text="3 / 4 · 교전 능력")
    
    # ------------------------------------------------------------
    # Page 4: weakness synthesis
    # ------------------------------------------------------------
    weakness_embed = discord.Embed(
        title=f"🩹 약점 - {patch_label}",
        description=f"🎮 **{player_name}**\n🏹 `{role}` · **{champion}**",
        color=0xe74c3c,
    )
    weakness_lines = []
    
    # Early lane collapse.
    if early:
        last = early[-1]
        if last["opp"]:
            gold_gap = int(last["row"]["total_gold"]) - int(last["opp"]["total_gold"])
            death_15 = int(last["row"].get("deaths", 0))
            my_level = level_from_xp(last["row"].get("xp", 0))
            opp_level = level_from_xp(last["opp"].get("xp", 0))
            my_cs = int(last["row"].get("lane_cs", 0) or 0)
            opp_cs = int(last["opp"].get("lane_cs", 0) or 0)
            lane_cs_weak = role != "서폿" and my_cs + 15 <= opp_cs
            if gold_gap <= -800 or my_level < opp_level or lane_cs_weak:
                cs_text = "" if role == "서폿" else f" · CS `{my_cs}` vs `{opp_cs}`"
                weakness_lines.append(
                    f"🌱 **초반 성장 열세**\n"
                    f"└ {last['minute']}분 전후 골드 `{int(last['row']['total_gold']):,}G` vs "
                    f"`{int(last['opp']['total_gold']):,}G` · 레벨 `{my_level}` vs `{opp_level}`"
                    f"{cs_text} · 데스 `{death_15}`"
                )
    
    if windows and role != "서폿":
        weakest = min(windows, key=lambda item: item.get("gold_gap_change", item["gold_pm"] - item["opp_gold_pm"]))
        resource_weak = (
            weakest["cs_pm"] + 1.5 < weakest["opp_cs_pm"]
            or weakest["gold_pm"] + 120 < weakest["opp_gold_pm"]
        )
        if resource_weak:
            cs_text = f" · CS `+{weakest['cs_gain']}` vs `+{weakest['opp_cs_gain']}`"
            weakness_lines.append(
                f"🧭 **중반 성장 격차 확대**\n"
                f"└ {weakest['start']}~{weakest['end']}분 골드 획득 `{weakest['gold_gain']:,}G` vs "
                f"`{weakest['opp_gold_gain']:,}G`{cs_text}\n"
                f"└ 레벨 `{weakest['start_level']} → {weakest['end_level']}` vs 상대 "
                f"`{weakest['opp_start_level']} → {weakest['opp_end_level']}`"
            )
    
    if involved_fights:
        bad_fights = [fight for fight in involved_fights if fight["target_d"] and fight["outcome"] == "패배"]
        if bad_fights:
            worst_fight = min(bad_fights, key=lambda fight: fight["gold_gap_delta"])
            weakness_lines.append(
                f"⚔️ **패배 교전에서 사망**\n"
                f"└ {format_game_time(worst_fight['start_ms'])} · 본인 "
                f"`{worst_fight['target_k']}/{worst_fight['target_d']}/{worst_fight['target_a']}` · "
                f"팀 골드 `{gold_swing_text(worst_fight['gold_gap_delta'])}`"
            )
    
    # Biggest checkpoint-to-checkpoint relative gold loss.
    drops = []
    for prev, cur in zip(player_series, player_series[1:]):
        if not prev.get("opp") or not cur.get("opp"):
            continue
        pr, po = prev["row"], prev["opp"]
        cr, co = cur["row"], cur["opp"]
        my_gain = int(cr.get("total_gold", 0) or 0) - int(pr.get("total_gold", 0) or 0)
        opp_gain = int(co.get("total_gold", 0) or 0) - int(po.get("total_gold", 0) or 0)
        death_delta = int(cr.get("deaths", 0) or 0) - int(pr.get("deaths", 0) or 0)
        drops.append({
            "from": prev["minute"], "to": cur["minute"],
            "my_gain": my_gain, "opp_gain": opp_gain,
            "relative_loss": my_gain - opp_gain,
            "death_delta": death_delta,
        })
    if drops:
        worst_drop = min(drops, key=lambda item: item["relative_loss"])
        if worst_drop["relative_loss"] <= -500:
            death_note = f" · 데스 +{worst_drop['death_delta']}" if worst_drop["death_delta"] else ""
            weakness_lines.append(
                f"📉 **내가 밀린 구간**\n"
                f"└ {worst_drop['from']}~{worst_drop['to']}분 획득 골드 "
                f"`{worst_drop['my_gain']:,}G` vs 상대 `{worst_drop['opp_gain']:,}G`{death_note}"
            )
    
    # Detect a throw-like collapse only when a real lead existed first.
    # This intentionally uses confirmed checkpoint values only: opponent
    # growth gap, team gold gap, deaths, and detected fights.
    lead_collapses = []
    for prev, cur in zip(player_series, player_series[1:]):
        if not prev.get("opp") or not cur.get("opp"):
            continue
        pr, po = prev["row"], prev["opp"]
        cr, co = cur["row"], cur["opp"]
        prev_player_gold_gap = int(pr.get("total_gold", 0)) - int(po.get("total_gold", 0))
        cur_player_gold_gap = int(cr.get("total_gold", 0)) - int(co.get("total_gold", 0))
        prev_score_gap = float(pr.get("checkpoint_score", 0) or 0) - float(po.get("checkpoint_score", 0) or 0)
        cur_score_gap = float(cr.get("checkpoint_score", 0) or 0) - float(co.get("checkpoint_score", 0) or 0)
        prev_own_gold = int((prev.get("teams", {}).get(target_team) or {}).get("gold", 0) or 0)
        prev_enemy_gold = int((prev.get("teams", {}).get(enemy_team) or {}).get("gold", 0) or 0)
        cur_own_gold = int((cur.get("teams", {}).get(target_team) or {}).get("gold", 0) or 0)
        cur_enemy_gold = int((cur.get("teams", {}).get(enemy_team) or {}).get("gold", 0) or 0)
        prev_team_gap = prev_own_gold - prev_enemy_gold
        cur_team_gap = cur_own_gold - cur_enemy_gold
        death_delta = int(cr.get("deaths", 0) or 0) - int(pr.get("deaths", 0) or 0)
    
        had_clear_lead = (
            prev_player_gold_gap >= 700
            or prev_team_gap >= 1500
        )
        if not had_clear_lead or death_delta <= 0:
            continue
    
        player_gold_swing = cur_player_gold_gap - prev_player_gold_gap
        score_swing = cur_score_gap - prev_score_gap
        team_gold_swing = cur_team_gap - prev_team_gap
        nearby_lost_fight = next((
            fight for fight in involved_fights
            if fight["outcome"] == "패배" and fight["target_d"]
            and prev["source_time_ms"] - 30_000 <= fight["start_ms"] <= cur["source_time_ms"] + 30_000
        ), None)
        severe_loss = (
            player_gold_swing <= -700
            or team_gold_swing <= -1200
            or nearby_lost_fight is not None
        )
        if not severe_loss:
            continue
    
        severity = (
            max(0, -player_gold_swing) / 350.0
            + max(0, -team_gold_swing) / 600.0
            + (3.0 if nearby_lost_fight else 0.0)
        )
        lead_collapses.append({
            "from": prev["minute"],
            "to": cur["minute"],
            "prev_player_gold_gap": prev_player_gold_gap,
            "cur_player_gold_gap": cur_player_gold_gap,
            "prev_score_gap": prev_score_gap,
            "cur_score_gap": cur_score_gap,
            "prev_team_gap": prev_team_gap,
            "cur_team_gap": cur_team_gap,
            "death_delta": death_delta,
            "nearby_lost_fight": nearby_lost_fight,
            "severity": severity,
        })
    
    if lead_collapses:
        collapse = max(lead_collapses, key=lambda item: item["severity"])
        fight_note = " · 패배 한타와 겹침" if collapse["nearby_lost_fight"] else ""
        weakness_lines.insert(0,
            f"💥 **큰 리드 이후 급격한 붕괴**\n"
            f"└ {collapse['from']}→{collapse['to']}분 · 데스 +{collapse['death_delta']}{fight_note}\n"
            f"└ 개인 {gold_gap_delta_text(collapse['prev_player_gold_gap'], collapse['cur_player_gold_gap'])}\n"
            f"└ 팀 {gold_gap_delta_text(collapse['prev_team_gap'], collapse['cur_team_gap'], label='골드차이')}"
        )
    
    if not weakness_lines:
        weakness_lines.append("뚜렷하게 큰 손실로 분류할 만한 구간이 적습니다.")
    
    good_lines = []
    if early and early[-1].get("opp"):
        last_early = early[-1]
        early_gold_gap = int(last_early["row"].get("total_gold", 0) or 0) - int(last_early["opp"].get("total_gold", 0) or 0)
        early_level_gap = level_from_xp(last_early["row"].get("xp", 0)) - level_from_xp(last_early["opp"].get("xp", 0))
        if early_gold_gap >= 500 or early_level_gap > 0:
            good_lines.append(
                f"🌱 **초반 성장 우위** · {last_early['minute']}분 전후 골드 `{early_gold_gap:+,}G` · 레벨차 `{early_level_gap:+d}`"
            )
    my_quest = quest_time_ms(participant_id)
    opp_quest = quest_time_ms(opponent_id) if opponent_id else 0
    if my_quest and opp_quest and my_quest < opp_quest:
        good_lines.append(f"🎯 **퀘스트 선완료** · 상대보다 `{(opp_quest-my_quest)//1000}초` 빠름")
    my_tower_takedowns = [event for event in tower_events if participant_id in [int(pid) for pid in event.get("takedown_ids", [])]]
    if my_tower_takedowns:
        good_lines.append(f"🏰 **타워 철거 관여** · `{len(my_tower_takedowns)}`회")
    fight_wins = sum(fight["outcome"] == "승리" for fight in involved_fights)
    fight_losses = sum(fight["outcome"] == "패배" for fight in involved_fights)
    if fight_wins > fight_losses and involved_fights:
        good_lines.append(f"⚔️ **교전 성과 우위** · 참여 `{len(involved_fights)}`회 중 `{fight_wins}승 {fight_losses}패`")
    if not good_lines:
        good_lines.append("뚜렷한 강점은 추가 표본과 함께 확인하는 것이 좋습니다.")

    weakness_embed.title = f"📋 총정리 - {patch_label}"
    weakness_embed.color = 0x9b59b6
    weakness_embed.add_field(
        name="✨ 좋은점",
        value="\n".join(good_lines[:4]),
        inline=False,
    )
    weakness_embed.add_field(
        name="🛠️ 보완점",
        value="\n\n".join(weakness_lines[:4]),
        inline=False,
    )
    weakness_embed.set_footer(text="4 / 4 · 총정리")
    
    # ------------------------------------------------------------
    # Role-specific coaching analysis pages
    # ------------------------------------------------------------
    # The generic calculations above remain as the factual data layer.
    # User-facing pages are reorganized by role so each position sees the
    # metrics that are actually useful for coaching that role.
    max_game_minute = max((item["minute"] for item in player_series), default=0) + 1
    early_activity_all = interval_participation(participant_id, target_team, 0, 15)
    full_activity = interval_participation(participant_id, target_team, 0, max_game_minute)
    opponent_full_activity = (
        interval_participation(opponent_id, enemy_team, 0, max_game_minute)
        if opponent_id else {}
    )
    
    fight_survived = sum(int(fight.get("target_d", 0) or 0) == 0 for fight in involved_fights)
    fight_deaths = sum(int(fight.get("target_d", 0) or 0) for fight in involved_fights)
    fight_takedowns = sum(int(fight.get("target_k", 0) or 0) + int(fight.get("target_a", 0) or 0) for fight in involved_fights)
    fight_survival_rate = (fight_survived / len(involved_fights) * 100.0) if involved_fights else 0.0
    
    measured_fights = [fight for fight in involved_fights if fight.get("combat_window")]
    measured_dpm_rows = []
    for fight in measured_fights:
        cw = fight.get("combat_window") or {}
        duration_ms = int(cw.get("duration_ms", 0) or 0)
        dealt = float(cw.get("damage_to_champions", 0) or 0)
        if duration_ms > 0:
            measured_dpm_rows.append({
                "fight": fight,
                "dealt": dealt,
                "dpm": dealt * 60_000.0 / duration_ms,
            })
    avg_measured_dpm = (
        sum(row["dpm"] for row in measured_dpm_rows) / len(measured_dpm_rows)
        if measured_dpm_rows else 0.0
    )
    
    def add_fight_log(embed, limit=5, include_damage=True):
        if not involved_fights:
            embed.add_field(name="📌 교전 기록", value="3인 이상 교전에 직접 참여한 기록이 없습니다.", inline=False)
            return
        lines = []
        for fight in involved_fights[:limit]:
            icon = "🔵" if fight["outcome"] == "승리" else "🔴" if fight["outcome"] == "패배" else "⚪"
            takedowns = int(fight.get("target_k", 0) or 0) + int(fight.get("target_a", 0) or 0)
            team_kills = max(0, int(fight.get("own_kills", 0) or 0))
            participation = f"{takedowns}/{team_kills}" if team_kills else "0/0"
            survived = int(fight.get("target_d", 0) or 0) == 0
            influence_bits = [f"킬관여 `{participation}`", "생존" if survived else "사망"]
            rank = fight.get("target_damage_rank")
            rank_total = int(fight.get("target_damage_rank_total", 0) or 0)
            if include_damage and rank and rank_total >= 2:
                influence_bits.insert(1, f"아군딜 `{rank}/{rank_total}위`")
            line = (
                f"{icon} **{format_game_time(fight['start_ms'])} · {fight['outcome']} "
                f"({fight['own_kills']}:{fight['enemy_kills']})**\n"
                f"└ " + " · ".join(influence_bits) +
                f" · 팀 `{gold_swing_text(fight['gold_gap_delta'])}`"
            )
            cw = fight.get("combat_window")
            if include_damage and cw:
                dealt = int(round(float(cw.get("damage_to_champions", 0) or 0)))
                line += f"\n└ 측정구간 챔피언딜 `{dealt:,}`"
            lines.append(line)
        embed.add_field(name="🔥 교전 영향력", value="\n\n".join(lines), inline=False)
    
    def compact_impact_line(row, counterpart_label=None):
        kd = int(row.get("kills", 0) or 0)
        ad = int(row.get("assists", 0) or 0)
        delta = int(row.get("gold_gap_delta", 0) or 0)
        if delta > 0:
            result = f"팀 `+{delta:,}G`"
        elif delta < 0:
            result = f"팀 `-{abs(delta):,}G`"
        else:
            result = "팀 `±0G`"
        line = f"• **{format_game_time(row['start_ms'])}** · `{kd}킬 {ad}어시` · {result}"
        if counterpart_label:
            line += f" · {counterpart_label} `{int(row.get('counterpart_takedowns', 0) or 0)}관여`"
        return line
    
    def add_compact_impact_highlights(embed, pid, team_name, counterpart_pid=0, counterpart_label=None,
                                      start_ms=0, end_ms=None, field_name="🎯 영향력 장면", limit=3):
        rows = participation_impact_windows(
            pid, team_name, counterpart_pid=counterpart_pid,
            start_ms=start_ms, end_ms=end_ms,
        )
        if not rows:
            embed.add_field(name=field_name, value="해당 구간에서 킬/어시스트 관여 기록이 없습니다.", inline=False)
            return []
        ranked = sorted(
            rows,
            key=lambda r: (
                int(r.get("gold_gap_delta", 0) or 0),
                int(r.get("takedowns", 0) or 0),
            ),
            reverse=True,
        )
        chosen = sorted(ranked[:limit], key=lambda r: int(r.get("start_ms", 0) or 0))
        embed.add_field(
            name=field_name,
            value="\n".join(compact_impact_line(row, counterpart_label) for row in chosen),
            inline=False,
        )
        return rows
    
    def add_top_team_gain(embed):
        if not windows:
            embed.add_field(name="📌 팀 이득", value="라인전 이후 비교할 구간 데이터가 부족합니다.", inline=False)
            return
        rows = []
        for item in windows:
            before = series_at_minute(item["start"])
            after = series_at_minute(item["end"])
            before_gap = _team_gold_gap_from_series(before, target_team)
            after_gap = _team_gold_gap_from_series(after, target_team)
            team_delta = after_gap - before_gap
            start_ms = int(before.get("source_time_ms", 0) or 0) if before else item["start"] * 60_000
            end_ms = int(after.get("source_time_ms", 0) or 0) if after else item["end"] * 60_000
            objs = [
                obj for obj in objective_events
                if str(obj.get("team") or "") == str(target_team)
                and start_ms <= int(obj.get("time_ms", 0) or 0) <= end_ms
            ]
            rows.append((int(item.get("gold_gain", 0) or 0), team_delta, item, objs))
        rows.sort(key=lambda x: x[0], reverse=True)
        lines = []
        obj_map = {"DRAGON":"드래곤", "RIFT_HERALD":"전령", "BARON":"바론", "ELDER_DRAGON":"장로"}
        for my_gain, team_delta, item, objs in rows[:3]:
            if team_delta > 0:
                team_text = f"팀 격차 `+{team_delta:,}G 개선`"
            elif team_delta < 0:
                team_text = f"팀 격차 `-{abs(team_delta):,}G 악화`"
            else:
                team_text = "팀 격차 `변화 없음`"
            obj_names = [obj_map.get(str(obj.get("name") or "").upper(), str(obj.get("name") or "오브젝트")) for obj in objs]
            obj_text = " · 오브젝트 `" + ", ".join(obj_names) + "`" if obj_names else ""
            lines.append(
                f"• **{item['start']}~{item['end']}분** · 내 골드 `+{my_gain:,}G` · {team_text}{obj_text}"
            )
        embed.add_field(name="💰 내가 성장한 동안 팀 결과", value="\n".join(lines), inline=False)
    
    def add_growth_overall(embed):
        comparable = [item for item in player_series if item.get("opp")]
        if len(comparable) < 2:
            embed.add_field(name="📌 성장 비교", value="상대와 비교할 성장 데이터가 부족합니다.", inline=False)
            return
        start = comparable[0]
        end = comparable[-1]
        sr, er = start["row"], end["row"]
        so, eo = start["opp"], end["opp"]
        my_start_cs = int(sr.get("lane_cs", 0) or 0) + int(sr.get("jungle_cs", 0) or 0)
        my_end_cs = int(er.get("lane_cs", 0) or 0) + int(er.get("jungle_cs", 0) or 0)
        op_start_cs = int(so.get("lane_cs", 0) or 0) + int(so.get("jungle_cs", 0) or 0)
        op_end_cs = int(eo.get("lane_cs", 0) or 0) + int(eo.get("jungle_cs", 0) or 0)
        start_gap = int(sr.get("total_gold", 0) or 0) - int(so.get("total_gold", 0) or 0)
        end_gap = int(er.get("total_gold", 0) or 0) - int(eo.get("total_gold", 0) or 0)
        lines = [
            f"💰 골드 차이 {gold_gap_delta_text(start_gap, end_gap)}",
            f"⬆️ 레벨 `{level_from_xp(sr.get('xp', 0))} → {level_from_xp(er.get('xp', 0))}` "
            f"vs 상대 `{level_from_xp(so.get('xp', 0))} → {level_from_xp(eo.get('xp', 0))}`",
        ]
        if role != "서폿":
            lines.insert(1, f"🌾 CS `{my_start_cs} → {my_end_cs}` vs 상대 `{op_start_cs} → {op_end_cs}`")
        embed.add_field(name="📈 경기 전체 성장 격차", value="\n".join(lines), inline=False)
    
    def stats_for_row(row):
        return ((row or {}).get("rofl_stats") or {})
    
    def team_objective_totals(team_name):
        totals = {"DRAGON_KILLS": 0, "BARON_KILLS": 0, "RIFT_HERALD_KILLS": 0, "ELDER_DRAGON_KILLS": 0}
        for row in rofl_rows:
            if str(row.get("team") or "") != str(team_name or ""):
                continue
            rs = stats_for_row(row)
            for key in totals:
                totals[key] += int(float(rs.get(key, 0) or 0))
        return totals
    
    # Optional objective timestamps. Some decoder builds expose these while
    # others only expose final objective counters. Never fabricate them.
    raw_objective_events = (
        checkpoint_analysis.get("objective_events")
        or checkpoint_analysis.get("objectives")
        or []
    )
    objective_events = []
    if isinstance(raw_objective_events, list):
        for event in raw_objective_events:
            if not isinstance(event, dict):
                continue
            time_ms = int(event.get("time_ms", event.get("timestamp", 0)) or 0)
            if not time_ms:
                continue
            killer_id = int(event.get("killer_id", event.get("participant_id", 0)) or 0)
            event_team = str(event.get("team") or participant_team.get(killer_id) or "")
            objective_name = str(event.get("objective") or event.get("type") or event.get("name") or "오브젝트")
            objective_events.append({
                "time_ms": time_ms,
                "killer_id": killer_id,
                "team": event_team,
                "name": objective_name,
                "stolen": bool(event.get("stolen", False)),
            })
    

    def objective_fight_analysis(obj):
        """
        Analyze events around one objective without implying causation.

        ROFL kill coordinates are not yet production-validated, so this
        code never claims that every kill in the time window happened
        at the dragon/herald/baron pit.

        Classification:
        - linked fight: target jungler, opposing jungler, or objective
          killer participated in a kill event in the window.
        - other fight: kill events occurred, but none of those anchor
          players participated.
        - no kill fight: no champion kill event in the window.
        """
        obj_ms = int(obj.get("time_ms", 0) or 0)
        if not obj_ms:
            return None

        scene_start = max(0, obj_ms - 40_000)
        scene_end = obj_ms + 25_000
        scene_events = [
            event for event in kill_events
            if scene_start <= int(event.get("time_ms", 0) or 0) <= scene_end
        ]

        objective_killer_id = int(obj.get("killer_id", 0) or 0)
        anchor_ids = {participant_id}
        if opponent_id:
            anchor_ids.add(int(opponent_id))
        if objective_killer_id:
            anchor_ids.add(objective_killer_id)

        linked_events = []
        other_events = []
        for event in scene_events:
            people = {
                int(event.get("killer_id", 0) or 0),
                int(event.get("victim_id", 0) or 0),
            }
            people.update(int(x) for x in event.get("assist_ids", []) if int(x))
            people.discard(0)
            if people & anchor_ids:
                linked_events.append(event)
            else:
                other_events.append(event)

        def summarize_events(events):
            blue_kills = red_kills = 0
            target_k = target_d = target_a = 0
            opponent_k = opponent_d = opponent_a = 0
            involved_people = set()

            for event in events:
                killer = int(event.get("killer_id", 0) or 0)
                victim = int(event.get("victim_id", 0) or 0)
                assists = [int(x) for x in event.get("assist_ids", []) if int(x)]

                if killer:
                    involved_people.add(killer)
                if victim:
                    involved_people.add(victim)
                involved_people.update(assists)

                killer_team = participant_team.get(killer)
                if killer_team == "blue":
                    blue_kills += 1
                elif killer_team == "red":
                    red_kills += 1

                target_k += int(killer == participant_id)
                target_d += int(victim == participant_id)
                target_a += int(participant_id in assists)

                if opponent_id:
                    opponent_k += int(killer == opponent_id)
                    opponent_d += int(victim == opponent_id)
                    opponent_a += int(opponent_id in assists)

            own_kills = blue_kills if target_team == "blue" else red_kills
            enemy_kills = red_kills if target_team == "blue" else blue_kills

            return {
                "own_kills": own_kills,
                "enemy_kills": enemy_kills,
                "target_involved": participant_id in involved_people,
                "target_k": target_k,
                "target_d": target_d,
                "target_a": target_a,
                "opponent_involved": bool(opponent_id and int(opponent_id) in involved_people),
                "opponent_k": opponent_k,
                "opponent_d": opponent_d,
                "opponent_a": opponent_a,
                "people": involved_people,
            }

        linked = summarize_events(linked_events)
        other = summarize_events(other_events)

        before = series_before_ms(scene_start)
        after = series_after_ms(scene_end)
        gap_before = _team_gold_gap_from_series(before, target_team)
        gap_after = _team_gold_gap_from_series(after, target_team)

        if linked_events:
            if linked["own_kills"] > linked["enemy_kills"]:
                scene_type = "linked_fight"
                exchange = "연결 교전 승리"
            elif linked["own_kills"] < linked["enemy_kills"]:
                scene_type = "linked_fight"
                exchange = "연결 교전 패배"
            else:
                scene_type = "linked_fight"
                exchange = "연결 교전 킬 교환"
        elif other_events:
            scene_type = "other_fight"
            exchange = "동시간대 다른 교전"
        else:
            scene_type = "no_fight"
            exchange = "킬 교전 없음"

        follow_end = obj_ms + 120_000
        follow_towers = [
            event for event in tower_events
            if obj_ms <= int(event.get("time_ms", 0) or 0) <= follow_end
        ]
        follow_objectives = [
            event for event in objective_events
            if obj_ms < int(event.get("time_ms", 0) or 0) <= follow_end
        ]

        return {
            "scene_type": scene_type,
            "exchange": exchange,
            "linked": linked,
            "other": other,
            "gold_gap_before": gap_before,
            "gold_gap_after": gap_after,
            "gold_gap_delta": gap_after - gap_before,
            "follow_towers": follow_towers,
            "follow_objectives": follow_objectives,
        }

    def compact_fight_champions(people, *, limit=5):
        labels = []
        for pid in sorted(int(x) for x in people if int(x)):
            label = participant_label(pid)
            if label not in labels:
                labels.append(label)
        return ", ".join(labels[:limit]) if labels else "참가자 미확인"

    def compact_followup_tower(event):
        lane_name = {
            "TOP": "탑",
            "MID": "미드",
            "BOT": "바텀",
            "NEXUS": "넥서스",
        }.get(str(event.get("lane") or ""), str(event.get("lane") or "?"))
        tower_name = {
            "OUTER_TURRET": "1차",
            "INNER_TURRET": "2차",
            "BASE_TURRET": "3차",
            "NEXUS_TURRET": "넥서스 포탑",
        }.get(str(event.get("tower_type") or ""), str(event.get("tower_type") or "포탑"))
        attacker = "우리팀" if str(event.get("team") or "") == target_team else "상대팀"
        return f"{lane_name} {tower_name} ({attacker})"

    def role_matchup_header(role_name=None):
        role_name = str(role_name or role)
        opp_champ = opponent_champion_name
        return f"⚔️ **{role_name} · {champion} vs {opp_champ}**"

    def gap_change_text(delta, *, subject="골드차이"):
        delta = int(delta or 0)
        if delta > 0:
            return f"{subject} **+{delta:,}G**"
        if delta < 0:
            return f"{subject} **-{abs(delta):,}G**"
        return f"{subject} **0G**"

    def line_gold_gap_state(value):
        value = int(value or 0)
        if value > 0:
            return f"상대 탑보다 +{value:,}G"
        if value < 0:
            return f"상대 탑보다 -{abs(value):,}G"
        return "상대 탑과 골드 동률"

    def top_enemy_outer_tower():
        rows = [
            event for event in tower_events
            if str(event.get("lane") or "") == "TOP"
            and str(event.get("tower_type") or "") == "OUTER_TURRET"
            and str(event.get("team") or "") == target_team
            and str(event.get("tower_team") or "") != target_team
        ]
        rows.sort(key=lambda event: int(event.get("time_ms", 0) or 0))
        return rows[0] if rows else None

    def top_quest_compare_text():
        mine = quest_time_ms(participant_id)
        theirs = quest_time_ms(opponent_id) if opponent_id else 0
        my_champ = str(champion or "내 챔피언")
        opp_champ = opponent_champion_name
        if not mine:
            return "퀘스트 완료 시간을 복원하지 못했습니다."
        if not theirs:
            return f"{my_champ} **{format_game_time(mine)}**"
        diff_sec = int(round((mine - theirs) / 1000.0))
        if diff_sec < 0:
            return f"✅ **{my_champ} {format_game_time(mine)}** vs **{opp_champ} {format_game_time(theirs)}** · **-{abs(diff_sec)}초**"
        if diff_sec > 0:
            return f"⚠️ **{my_champ} {format_game_time(mine)}** vs **{opp_champ} {format_game_time(theirs)}** · **+{diff_sec}초**"
        return f"➖ **{my_champ} {format_game_time(mine)}** vs **{opp_champ} {format_game_time(theirs)}** · 동일"

    def top_prequest_swings():
        mine = quest_time_ms(participant_id)
        cutoff = mine if mine else 15 * 60_000
        comparable = [item for item in player_series if item.get("opp") and int(item.get("source_time_ms", 0) or 0) <= cutoff]
        rows = []
        for prev, cur in zip(comparable, comparable[1:]):
            pr, po, cr, co = prev["row"], prev["opp"], cur["row"], cur["opp"]
            start_gap = int(pr.get("total_gold", 0) or 0) - int(po.get("total_gold", 0) or 0)
            end_gap = int(cr.get("total_gold", 0) or 0) - int(co.get("total_gold", 0) or 0)
            rows.append({
                "from": prev["minute"], "to": cur["minute"],
                "start_gap": start_gap, "end_gap": end_gap, "gap_change": end_gap - start_gap,
                "my_gain": int(cr.get("total_gold", 0) or 0) - int(pr.get("total_gold", 0) or 0),
                "opp_gain": int(co.get("total_gold", 0) or 0) - int(po.get("total_gold", 0) or 0),
                "my_cs_gain": int(cr.get("lane_cs", 0) or 0) - int(pr.get("lane_cs", 0) or 0),
                "opp_cs_gain": int(co.get("lane_cs", 0) or 0) - int(po.get("lane_cs", 0) or 0),
            })
        return rows

    def top_swing_text(item):
        if not item:
            return "비교할 구간 데이터가 부족합니다."
        return (
            f"**{item['from']}~{item['to']}분**\n"
            f"└ 💰 vs `{opponent_top_champion_name}` 골드차이 `{item['gap_change']:+,}G`\n"
            f"└ 획득 골드 `나 +{item['my_gain']:,}G` / `상대 +{item['opp_gain']:,}G`\n"
            f"└ 🌾 CS 획득 `나 +{item['my_cs_gain']}` / `상대 +{item['opp_cs_gain']}`"
        )

    def top_side_operation_text(tower):
        if not tower:
            return "상대 탑 1차 포탑 파괴 시점을 복원하지 못했습니다."
        start_ms = int(tower.get("time_ms", 0) or 0)
        end_ms = min(start_ms + 5 * 60_000, int(player_series[-1].get("source_time_ms", 0) or 0))
        before, after = series_before_ms(start_ms), series_after_ms(end_ms)
        if not before or not after or not before.get("opp") or not after.get("opp"):
            return "1차 포탑 이후 5분 성장 비교 데이터가 부족합니다."
        br, bo, ar, ao = before["row"], before["opp"], after["row"], after["opp"]
        start_personal_gap = int(br.get("total_gold", 0) or 0) - int(bo.get("total_gold", 0) or 0)
        end_personal_gap = int(ar.get("total_gold", 0) or 0) - int(ao.get("total_gold", 0) or 0)
        my_gain = int(ar.get("total_gold", 0) or 0) - int(br.get("total_gold", 0) or 0)
        opp_gain = int(ao.get("total_gold", 0) or 0) - int(bo.get("total_gold", 0) or 0)
        relative_gain = my_gain - opp_gain
        team_gap_before = _team_gold_gap_from_series(before, target_team)
        team_gap_after = _team_gold_gap_from_series(after, target_team)

        obj_map = {"DRAGON":"드래곤", "RIFT_HERALD":"전령", "BARON":"바론", "ELDER_DRAGON":"장로"}
        obj_lines = []
        for obj in [x for x in objective_events if start_ms <= int(x.get("time_ms", 0) or 0) <= end_ms][:4]:
            side = "우리팀" if str(obj.get("team") or "") == target_team else "상대팀"
            obj_lines.append(f"{obj_map.get(str(obj.get('name') or '').upper(), str(obj.get('name') or '오브젝트'))} {side} 획득")

        tower_lines = []
        for event in [
            x for x in tower_events
            if start_ms <= int(x.get("time_ms", 0) or 0) <= end_ms
            and participant_id in [int(pid) for pid in x.get("takedown_ids", [])]
        ][:4]:
            lane = {"TOP":"탑","MID":"미드","BOT":"바텀","NEXUS":"넥서스"}.get(str(event.get("lane") or ""), "?")
            tier = {"OUTER_TURRET":"1차","INNER_TURRET":"2차","BASE_TURRET":"3차","NEXUS_TURRET":"넥서스 포탑"}.get(str(event.get("tower_type") or ""), "포탑")
            tower_lines.append(f"{lane} {tier}")

        rel_text = f"상대 탑보다 **{relative_gain:+,}G 더 획득**" if relative_gain else "상대 탑과 **같은 골드 획득**"
        lines = [
            f"**{format_game_time(start_ms)} ~ {format_game_time(end_ms)}**",
            f"└ 💰 {rel_text}",
            f"└ vs `{opponent_top_champion_name}` 골드차이 `{(end_personal_gap-start_personal_gap):+,}G`",
            f"└ 🧮 {gold_gap_delta_text(team_gap_before, team_gap_after, label='팀 골드차이')}",
        ]
        if obj_lines:
            lines.append("└ 🐉 오브젝트 `" + " · ".join(obj_lines) + "`")
        if tower_lines:
            lines.append("└ 🏰 본인 철거 관여 `" + " · ".join(tower_lines) + "`")
        return "\n".join(lines)

    def top_lane_2v2_fights(tower):
        tower_ms = int((tower or {}).get("time_ms", 15 * 60_000) or 15 * 60_000)
        start_ms, end_ms = max(0, tower_ms - 6 * 60_000), tower_ms + 2 * 60_000
        rows = []
        for fight in teamfights:
            if not (start_ms <= int(fight.get("start_ms", 0) or 0) <= end_ms) or not fight.get("target_involved"):
                continue
            scene = [event for event in kill_events if int(fight.get("start_ms", 0) or 0) <= int(event.get("time_ms", 0) or 0) <= int(fight.get("end_ms", 0) or 0)]
            if not any(opponent_id and int(opponent_id) in kill_participants(event) for event in scene):
                continue
            if int(fight.get("blue_people_count", 0) or 0) < 2 or int(fight.get("red_people_count", 0) or 0) < 2:
                continue
            rows.append(fight)
        return rows

    def top_fight_line(fight):
        share = fight.get("target_damage_share")
        share_text = f" · 교전 데미지 비중 **{share:.0f}%**" if share is not None else ""
        return (
            f"{'🟢' if fight['outcome']=='승리' else '🔴' if fight['outcome']=='패배' else '⚪'} "
            f"**{format_game_time(fight['start_ms'])} · {fight['own_kills']}:{fight['enemy_kills']} {fight['outcome']}**{share_text}\n"
            f"└ {gold_gap_delta_text(fight['gold_gap_before'], fight['gold_gap_after'], label='팀 골드차이')}"
        )

    def top_post_tower_objective_lines(tower, limit=4):
        if not tower:
            return []
        tower_ms = int(tower.get("time_ms", 0) or 0)
        rows, obj_map = [], {"DRAGON":"드래곤","RIFT_HERALD":"전령","BARON":"바론","ELDER_DRAGON":"장로"}
        for obj in sorted(objective_events, key=lambda x: int(x.get("time_ms", 0) or 0)):
            obj_ms = int(obj.get("time_ms", 0) or 0)
            if obj_ms <= tower_ms:
                continue
            analysis = objective_fight_analysis(obj)
            name = obj_map.get(str(obj.get("name") or "").upper(), str(obj.get("name") or "오브젝트"))
            side = "우리팀 획득" if str(obj.get("team") or "") == target_team else "상대팀 획득"
            line = f"{'🟢' if str(obj.get('team') or '') == target_team else '🔴'} **{format_game_time(obj_ms)} · {name} {side}**"
            if analysis:
                if analysis["scene_type"] == "linked_fight":
                    linked = analysis["linked"]
                    line += f"\n└ ⚔️ 교전 `{linked['own_kills']}:{linked['enemy_kills']}`"
                    nearby = min(
                        (fight for fight in teamfights if abs(int(fight.get("start_ms", 0) or 0) - obj_ms) <= 65_000 and fight.get("target_involved")),
                        key=lambda f: abs(int(f.get("start_ms", 0) or 0) - obj_ms), default=None
                    )
                    if nearby and nearby.get("target_damage_share") is not None:
                        line += f" · 교전 데미지 비중 **{nearby['target_damage_share']:.0f}%**"
                    elif not linked["target_involved"]:
                        line += " · 본인 미참여"
                elif analysis["scene_type"] == "other_fight":
                    other = analysis["other"]
                    line += f"\n└ 📍 동시간대 다른 교전 `{other['own_kills']}:{other['enemy_kills']}` · 본인 미참여"
                else:
                    line += "\n└ ⚪ 킬 교전 없음"
                line += f"\n└ {gold_gap_delta_text(analysis['gold_gap_before'], analysis['gold_gap_after'], label='팀 골드차이')}"
            rows.append(line)
            if len(rows) >= limit:
                break
        return rows

    def first_outer_tower_time_ms():
        times = [
            int(event.get("time_ms", 0) or 0)
            for event in tower_events
            if str(event.get("tower_type") or "") == "OUTER_TURRET"
            and int(event.get("time_ms", 0) or 0) > 0
        ]
        return min(times) if times else 15 * 60_000

    def participant_role(pid):
        row = next((x for x in participants if int(x.get("participant_id", 0) or 0) == int(pid or 0)), None)
        value = str((row or {}).get("role") or "").strip()
        aliases = {
            "TOP":"탑", "MIDDLE":"미드", "MID":"미드", "JUNGLE":"정글",
            "BOTTOM":"원딜", "BOT":"원딜", "UTILITY":"서폿", "SUPPORT":"서폿",
        }
        return aliases.get(value.upper(), value)

    def frame_player(pid, time_ms):
        if not frames:
            return None
        frame = min(frames, key=lambda item: abs(int(item.get("source_time_ms", 0) or 0) - int(time_ms or 0)))
        return next((x for x in frame.get("players", []) if int(x.get("participant_id", 0) or 0) == int(pid or 0)), None)

    def gold_of_pid(pid, time_ms):
        row = frame_player(pid, time_ms)
        return int((row or {}).get("total_gold", 0) or 0)

    def level_of_pid(pid, time_ms):
        row = frame_player(pid, time_ms)
        return level_from_xp(int((row or {}).get("xp", 0) or 0)) if row else 0

    def lane_pids(team_name, lane_name):
        wanted = {"탑":{"탑"}, "미드":{"미드"}, "바텀":{"원딜","서폿"}}.get(lane_name, set())
        return [
            int(x.get("participant_id", 0) or 0) for x in participants
            if participant_team.get(int(x.get("participant_id", 0) or 0)) == team_name
            and participant_role(int(x.get("participant_id", 0) or 0)) in wanted
        ]

    def lane_gold_gap_at(lane_name, time_ms, team_name):
        enemy = "red" if team_name == "blue" else "blue"
        own = sum(gold_of_pid(pid, time_ms) for pid in lane_pids(team_name, lane_name))
        opp = sum(gold_of_pid(pid, time_ms) for pid in lane_pids(enemy, lane_name))
        return own - opp

    def jungle_gold_gap_at(time_ms):
        if not opponent_id:
            return 0
        return gold_of_pid(participant_id, time_ms) - gold_of_pid(opponent_id, time_ms)

    def jungle_scene_lane(scene):
        scores = {"탑":0, "미드":0, "바텀":0}
        for event in scene:
            for pid in kill_participants(event):
                r = participant_role(pid)
                if r == "탑": scores["탑"] += 1
                elif r == "미드": scores["미드"] += 1
                elif r in {"원딜","서폿"}: scores["바텀"] += 1
        best = max(scores, key=scores.get)
        return best if scores[best] else "기타"

    def jungle_interventions(pid, team_name, cutoff_ms):
        windows = participation_impact_windows(pid, team_name, start_ms=0, end_ms=cutoff_ms, cluster_gap_ms=35_000)
        rows = []
        for row in windows:
            scene_start = max(0, int(row["start_ms"]) - 12_000)
            scene_end = int(row["end_ms"]) + 12_000
            scene = [e for e in kill_events if scene_start <= int(e.get("time_ms",0) or 0) <= scene_end]
            lane = jungle_scene_lane(scene)
            own_k = sum(1 for e in scene if participant_team.get(int(e.get("killer_id",0) or 0)) == team_name)
            enemy_team_name = "red" if team_name == "blue" else "blue"
            enemy_k = sum(1 for e in scene if participant_team.get(int(e.get("killer_id",0) or 0)) == enemy_team_name)
            after_2m = int(row["end_ms"]) + 120_000
            lane_before = lane_gold_gap_at(lane, int(row["end_ms"]), team_name) if lane != "기타" else 0
            lane_after = lane_gold_gap_at(lane, after_2m, team_name) if lane != "기타" else 0
            jg_before = jungle_gold_gap_at(int(row["end_ms"]))
            jg_after = jungle_gold_gap_at(after_2m)
            row = dict(row)
            row.update({
                "lane": lane, "own_kills": own_k, "enemy_kills": enemy_k,
                "lane_gap_before": lane_before, "lane_gap_after": lane_after,
                "lane_benefit": lane_after-lane_before,
                "jungle_gap_before": jg_before, "jungle_gap_after": jg_after,
                "jungle_cost": jg_after-jg_before,
            })
            rows.append(row)
        return rows

    def lane_champion_name(lane, team):
        lane_role = {"탑": "TOP", "미드": "MIDDLE", "바텀": "BOTTOM"}.get(str(lane))
        if not lane_role:
            return "챔피언"
        for actor in participants:
            if str(actor.get("team") or "") != str(team):
                continue
            position = str(actor.get("position") or actor.get("team_position") or "").upper()
            if position == lane_role:
                return str(actor.get("champion") or "챔피언")
        return "챔피언"

    def signed_change_word(value):
        value = int(value or 0)
        if value > 0:
            return f"+{value:,}G 개선"
        if value < 0:
            return f"-{abs(value):,}G 악화"
        return "0G 변화"

    def jungle_intervention_line(row):
        lane = str(row.get("lane") or "기타")
        exchange = f"{int(row.get('own_kills',0))}:{int(row.get('enemy_kills',0))} 교환"
        lane_delta = int(row.get("lane_benefit",0) or 0)
        jg_before = int(row.get("jungle_gap_before",0) or 0)
        jg_after = int(row.get("jungle_gap_after",0) or 0)
        jg_delta = jg_after - jg_before

        line = f"• **{format_game_time(row['start_ms'])} · {lane} · {exchange}**"
        if lane != "기타":
            ally_champion = lane_champion_name(lane, target_team)
            line += f"\n└ 🛣️ `({ally_champion})` 골드차이 **{lane_delta:+,}G (2분)**"

        enemy_jg_champion = opponent_jungle_champion_name
        line += f"\n└ 🌲 vs `({enemy_jg_champion})` 골드차이 **{jg_delta:+,}G (2분)**"
        return line

    def jungle_intervention_summary(my_rows, enemy_rows):
        lanes = ("탑", "미드", "바텀")
        lines = []
        for lane in lanes:
            mine = [x for x in my_rows if x.get("lane") == lane]
            benefit = sum(int(x.get("lane_benefit",0) or 0) for x in mine)
            ally_champion = lane_champion_name(lane, target_team)
            lines.append(
                f"**{lane} `({ally_champion})`** · 갱킹 이후 골드차이 **{benefit:+,}G**"
            )

        total_jungle_change = sum(
            int(x.get("jungle_gap_after",0) or 0) - int(x.get("jungle_gap_before",0) or 0)
            for x in my_rows
        )
        enemy_jg_champion = opponent_jungle_champion_name
        lines.append(
            f"🌲 **갱킹 이후 내 골드차이 vs `({enemy_jg_champion})`** · "
            f"**{total_jungle_change:+,}G**"
        )
        return "\n".join(lines)

    def jungle_growth_swings():
        cutoff = quest_time_ms(participant_id) or first_outer_tower_time_ms()
        comparable = [x for x in player_series if x.get("opp") and int(x.get("source_time_ms",0) or 0) <= cutoff]
        rows = []
        for prev, cur in zip(comparable, comparable[1:]):
            pr, po, cr, co = prev["row"], prev["opp"], cur["row"], cur["opp"]
            g0 = int(pr.get("total_gold",0) or 0)-int(po.get("total_gold",0) or 0)
            g1 = int(cr.get("total_gold",0) or 0)-int(co.get("total_gold",0) or 0)
            l0 = level_from_xp(pr.get("xp",0))-level_from_xp(po.get("xp",0))
            l1 = level_from_xp(cr.get("xp",0))-level_from_xp(co.get("xp",0))
            cs0 = (int(pr.get("jungle_cs",0) or 0)+int(pr.get("lane_cs",0) or 0))-(int(po.get("jungle_cs",0) or 0)+int(po.get("lane_cs",0) or 0))
            cs1 = (int(cr.get("jungle_cs",0) or 0)+int(cr.get("lane_cs",0) or 0))-(int(co.get("jungle_cs",0) or 0)+int(co.get("lane_cs",0) or 0))
            rows.append({"from":prev["minute"],"to":cur["minute"],"g0":g0,"g1":g1,"gd":g1-g0,"l0":l0,"l1":l1,"cs0":cs0,"cs1":cs1})
        return rows

    def jungle_growth_line(row):
        enemy_jg_champion = opponent_jungle_champion_name
        lines = [
            f"**{row['from']}~{row['to']}분**",
            f"└ 💰 vs `{enemy_jg_champion}` 골드차이 `{row['gd']:+,}G`",
        ]

        level_change = int(row["l1"] - row["l0"])
        cs_change = int(row["cs1"] - row["cs0"])

        if level_change != 0:
            lines.append(f"└ 📊 레벨차 변화 `{level_change:+d}`")
        if abs(cs_change) >= 10:
            lines.append(f"└ 🌾 CS차 변화 `{cs_change:+d}`")

        return "\n".join(lines)

    def objective_damage_share(obj_ms):
        nearby = min(
            (f for f in teamfights if f.get("target_involved") and abs(int(f.get("start_ms",0) or 0)-int(obj_ms)) <= 65_000),
            key=lambda f: abs(int(f.get("start_ms",0) or 0)-int(obj_ms)), default=None,
        )
        return float(nearby.get("target_damage_share")) if nearby and nearby.get("target_damage_share") is not None else None

    def jungle_early_growth_story():
        if role != "정글" or not opponent_id:
            return None

        rows = []
        for item in player_series:
            opp = item.get("opp")
            if not opp:
                continue
            minute = int(item.get("minute", 0) or 0)
            if minute > 12:
                continue

            me = item["row"]
            my_level = level_from_xp(me.get("xp", 0))
            opp_level = level_from_xp(opp.get("xp", 0))
            rows.append({
                "minute": minute,
                "gold_gap": int(me.get("total_gold", 0) or 0) - int(opp.get("total_gold", 0) or 0),
                "my_level": my_level,
                "opp_level": opp_level,
                "level_gap": my_level - opp_level,
                "jg_cs_gap": int(me.get("jungle_cs", 0) or 0) - int(opp.get("jungle_cs", 0) or 0),
            })

        meaningful = [
            row for row in rows
            if row["gold_gap"] <= -200
            or row["level_gap"] <= -1
            or row["jg_cs_gap"] <= -8
        ]
        if not meaningful:
            return None

        def severity(row):
            return (
                max(0, -row["gold_gap"]) / 200.0
                + max(0, -row["level_gap"]) * 1.5
                + max(0, -row["jg_cs_gap"]) / 8.0
            )

        low = max(meaningful, key=severity)
        low_index = rows.index(low)
        recovery = None
        reversal = None

        for row in rows[low_index + 1:]:
            if recovery is None and abs(row["gold_gap"]) <= 100:
                recovery = row
            if row["gold_gap"] >= 150:
                reversal = row
                break

        lines = [f"📉 **초반 최저점 · {low['minute']}분**"]
        if low["gold_gap"] < 0:
            lines.append(f"└ vs `{opponent_jungle_champion_name}` 골드차이 `{low['gold_gap']:+,}G`")
        if low["level_gap"] < 0:
            lines.append(f"└ 레벨 `{low['my_level']} vs {low['opp_level']}`")
        if low["jg_cs_gap"] <= -8:
            lines.append(f"└ 정글 CS `{abs(low['jg_cs_gap'])}`개 열세")

        if recovery:
            lines += [
                "",
                f"📈 **격차 회복 · {recovery['minute']}분**",
                f"└ vs `{opponent_jungle_champion_name}` 골드차이 `{recovery['gold_gap']:+,}G`",
            ]

        if reversal:
            lines += [
                "",
                f"🔄 **성장 역전 · {reversal['minute']}분**",
                f"└ vs `{opponent_jungle_champion_name}` 골드차이 `{reversal['gold_gap']:+,}G`",
            ]

        return "\n".join(lines)

    # ------------------------------------------------------------
    # Coaching-oriented common analysis helpers.
    # Keep the same four-page UX for every role, while changing only
    # the early-game cutoff and role-relevant emphasis.
    # ------------------------------------------------------------
    def analysis_early_cutoff(role_name):
        role_name = str(role_name or role)
        if role_name in {"탑", "원딜", "서폿"}:
            mine = quest_time_ms(participant_id)
            theirs = quest_time_ms(opponent_id) if opponent_id else 0
            # Early phase ends only when BOTH lane counterparts have completed
            # their role quest. If one marker is missing, fail closed to the
            # available marker instead of inventing an exact completion time.
            if mine and theirs:
                return max(mine, theirs), "quest_both"
            if mine or theirs:
                return max(mine, theirs), "quest_partial"
            return 15 * 60_000, "quest_missing"
        if role_name in {"정글", "미드"}:
            return first_outer_tower_time_ms(), "first_outer"
        return 15 * 60_000, "fallback"

    def analysis_early_cutoff_text(role_name):
        cutoff_ms, source = analysis_early_cutoff(role_name)
        if source == "quest_both":
            mine = quest_time_ms(participant_id)
            theirs = quest_time_ms(opponent_id) if opponent_id else 0
            return (
                f"**{format_game_time(cutoff_ms)}** · 나 `{format_game_time(mine)}` / "
                f"상대 `{format_game_time(theirs)}` 퀘스트 완료"
            )
        if source == "quest_partial":
            return f"**{format_game_time(cutoff_ms)}** · 한쪽 퀘스트 완료 시점만 복원됨"
        if source == "quest_missing":
            return "퀘스트 완료 시점을 모두 복원하지 못해 **15분**을 보조 기준으로 사용"
        if source == "first_outer":
            tower = min(
                (
                    event for event in tower_events
                    if str(event.get("tower_type") or "") == "OUTER_TURRET"
                    and int(event.get("time_ms", 0) or 0) > 0
                ),
                key=lambda event: int(event.get("time_ms", 0) or 0),
                default=None,
            )
            if tower:
                lane = {"TOP":"탑", "MID":"미드", "BOT":"바텀"}.get(str(tower.get("lane") or ""), "라인")
                return f"**{format_game_time(cutoff_ms)}** · 경기 첫 1차 포탑 파괴 ({lane})"
            return "1차 포탑 시점을 복원하지 못해 **15분**을 보조 기준으로 사용"
        return f"**{format_game_time(cutoff_ms)}**"

    def analysis_early_summary(role_name):
        cutoff_ms, _source = analysis_early_cutoff(role_name)
        point = series_before_ms(cutoff_ms)
        if not point or not point.get("opp"):
            return "초반 종료 시점의 맞상대 성장 데이터를 만들지 못했습니다."
        mine, theirs = point["row"], point["opp"]
        gold_gap = int(mine.get("total_gold", 0) or 0) - int(theirs.get("total_gold", 0) or 0)
        my_level = level_from_xp(mine.get("xp", 0))
        opp_level = level_from_xp(theirs.get("xp", 0))
        role_name = str(role_name or role)
        lines = [
            f"💰 골드 `{gold_gap:+,}G`",
            f"⬆️ 레벨 `{my_level} vs {opp_level}`",
        ]
        if role_name == "정글":
            cs_gap = int(mine.get("jungle_cs", 0) or 0) - int(theirs.get("jungle_cs", 0) or 0)
            lines.append(f"🌲 정글 CS `{cs_gap:+d}`")
        elif role_name != "서폿":
            cs_gap = int(mine.get("lane_cs", 0) or 0) - int(theirs.get("lane_cs", 0) or 0)
            lines.append(f"🌾 CS `{cs_gap:+d}`")
        # Give one plain-language verdict instead of exposing XP values.
        score = gold_gap / 450.0 + (my_level - opp_level) * 1.4
        if role_name == "정글":
            score += (int(mine.get("jungle_cs", 0) or 0) - int(theirs.get("jungle_cs", 0) or 0)) / 12.0
        elif role_name != "서폿":
            score += (int(mine.get("lane_cs", 0) or 0) - int(theirs.get("lane_cs", 0) or 0)) / 15.0
        verdict = "우세" if score >= 1.2 else "열세" if score <= -1.2 else "비슷"
        return f"**{verdict}** · " + " · ".join(lines)

    def analysis_early_detail(role_name):
        """Return one compact, role-relevant early-game note.

        This intentionally reuses facts already decoded for the report.  Small
        fluctuations stay hidden so the first page does not turn back into a
        checkpoint ledger.
        """
        role_name = str(role_name or role)
        cutoff_ms, _source = analysis_early_cutoff(role_name)
        lines = []

        # Quest lanes: show only the intuitive completion delta.
        if role_name in {"탑", "원딜", "서폿"}:
            mine = quest_time_ms(participant_id)
            theirs = quest_time_ms(opponent_id) if opponent_id else 0
            if mine and theirs:
                diff = int(round((theirs - mine) / 1000.0))
                if abs(diff) >= 15:
                    state = "빠름" if diff > 0 else "늦음"
                    lines.append(f"🎯 퀘스트 · 상대보다 **{abs(diff)}초 {state}**")

        # Role-specific early participation.  We do not call this a roam/gank
        # because reliable positional coordinates are not decoded yet.
        early_events = [e for e in kill_events if int(e.get("time_ms", 0) or 0) <= cutoff_ms]
        my_k = sum(1 for e in early_events if int(e.get("killer_id", 0) or 0) == participant_id)
        my_a = sum(1 for e in early_events if participant_id in [int(x) for x in e.get("assist_ids", [])])
        my_d = sum(1 for e in early_events if int(e.get("victim_id", 0) or 0) == participant_id)
        if role_name in {"정글", "미드", "서폿"} and (my_k + my_a or my_d):
            lines.append(f"⚔️ 초반 관여 · **{my_k}킬 {my_a}어시 / {my_d}데스**")

        # Jungle: first objective before the first outer tower is useful context.
        if role_name == "정글":
            early_objs = [o for o in objective_events if int(o.get("time_ms", 0) or 0) <= cutoff_ms]
            if early_objs:
                obj_map = {"DRAGON":"드래곤", "RIFT_HERALD":"전령", "BARON":"바론", "ELDER_DRAGON":"장로"}
                obj = sorted(early_objs, key=lambda o: int(o.get("time_ms", 0) or 0))[0]
                name = obj_map.get(str(obj.get("name") or "").upper(), str(obj.get("name") or "오브젝트"))
                side = "우리팀 획득" if str(obj.get("team") or "") == target_team else "상대팀 획득"
                lines.append(f"🐉 첫 오브젝트 · **{format_game_time(obj.get('time_ms', 0))} {name} {side}**")

        # Preserve the useful old 'caught up / widened' idea only when the
        # personal gold gap actually swings by a meaningful amount.
        pre = [item for item in player_series if int(item.get("source_time_ms", 0) or 0) <= cutoff_ms and item.get("opp")]
        best = None
        for prev, cur in zip(pre, pre[1:]):
            p0 = int(prev["row"].get("total_gold", 0) or 0) - int(prev["opp"].get("total_gold", 0) or 0)
            p1 = int(cur["row"].get("total_gold", 0) or 0) - int(cur["opp"].get("total_gold", 0) or 0)
            delta = p1 - p0
            if abs(delta) >= 700 and (best is None or abs(delta) > abs(best[0])):
                best = (delta, int(prev.get("minute", 0) or 0), int(cur.get("minute", 0) or 0))
        if best:
            delta, m0, m1 = best
            label = "격차 확대" if delta > 0 else "상대가 추격"
            lines.append(f"{'📈' if delta > 0 else '📉'} {m0}~{m1}분 **{label} {delta:+,}G**")

        return "\n".join(lines[:3])

    def _objective_near_fight(fight, radius_ms=75_000):
        start_ms = int(fight.get("start_ms", 0) or 0)
        return min(
            objective_events,
            key=lambda obj: abs(int(obj.get("time_ms", 0) or 0) - start_ms),
            default=None,
        ) if objective_events and min(
            (abs(int(obj.get("time_ms", 0) or 0) - start_ms) for obj in objective_events),
            default=10**12,
        ) <= radius_ms else None

    def analysis_key_fights(role_name, limit=4):
        cutoff_ms, _source = analysis_early_cutoff(role_name)
        rows = []
        for fight in teamfights:
            if not fight.get("target_involved"):
                continue
            if int(fight.get("start_ms", 0) or 0) < cutoff_ms:
                continue
            obj = _objective_near_fight(fight)
            importance = (
                abs(int(fight.get("gold_gap_delta", 0) or 0))
                + int(fight.get("deaths", 0) or 0) * 350
                + (1400 if obj is not None else 0)
            )
            rows.append((importance, int(fight.get("start_ms", 0) or 0), fight, obj))
        rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
        picked = rows[:limit]
        picked.sort(key=lambda item: item[1])
        return [(fight, obj) for _score, _time, fight, obj in picked]

    def analysis_fight_line(role_name, fight, obj=None):
        icon = "🟢" if fight.get("outcome") == "승리" else "🔴" if fight.get("outcome") == "패배" else "⚪"
        title = f"{icon} **{format_game_time(fight.get('start_ms', 0))} · {fight.get('own_kills',0)}:{fight.get('enemy_kills',0)} {fight.get('outcome','교전')}**"
        if obj:
            obj_name = {"DRAGON":"드래곤", "RIFT_HERALD":"전령", "BARON":"바론", "ELDER_DRAGON":"장로"}.get(str(obj.get("name") or "").upper(), str(obj.get("name") or "오브젝트"))
            title += f" · {obj_name} 인접"
        details = [
            f"└ 본인 `{int(fight.get('target_k',0) or 0)}/{int(fight.get('target_d',0) or 0)}/{int(fight.get('target_a',0) or 0)}`",
        ]
        if str(role_name) != "서폿" and fight.get("target_damage_share") is not None:
            details.append(f"└ 💥 팀 교전딜 비중 **{float(fight['target_damage_share']):.0f}%**")
        details.append(
            f"└ 💰 팀 골드차 `{int(fight.get('gold_gap_before',0) or 0):+,}G → {int(fight.get('gold_gap_after',0) or 0):+,}G`"
        )
        return title + "\n" + "\n".join(details)

    def analysis_swing_points(role_name, limit=3):
        cutoff_ms, _source = analysis_early_cutoff(role_name)
        rows = []
        for fight in teamfights:
            if not fight.get("target_involved") or int(fight.get("start_ms",0) or 0) < cutoff_ms:
                continue
            before = series_before_ms(int(fight.get("start_ms", 0) or 0))
            after = series_after_ms(int(fight.get("end_ms", 0) or 0) + 120_000)
            if not before or not after:
                continue
            before_gap = _team_gold_gap_from_series(before, target_team)
            after_gap = _team_gold_gap_from_series(after, target_team)
            delta = after_gap - before_gap
            if abs(delta) < 900:
                continue
            rows.append({"fight": fight, "before": before_gap, "after": after_gap, "delta": delta})
        rows.sort(key=lambda item: abs(item["delta"]), reverse=True)
        return rows[:limit]

    def analysis_death_mistakes(role_name, limit=2):
        cutoff_ms, _source = analysis_early_cutoff(role_name)
        rows = []
        for fight in teamfights:
            if int(fight.get("target_d", 0) or 0) <= 0 or int(fight.get("start_ms",0) or 0) < cutoff_ms:
                continue
            start_ms = int(fight.get("start_ms", 0) or 0)
            end_window = int(fight.get("end_ms", start_ms) or start_ms) + 120_000
            before = series_before_ms(start_ms)
            after = series_after_ms(end_window)
            if not before or not after:
                continue
            before_gap = _team_gold_gap_from_series(before, target_team)
            after_gap = _team_gold_gap_from_series(after, target_team)
            delta = after_gap - before_gap
            lost_objectives = [
                obj for obj in objective_events
                if start_ms <= int(obj.get("time_ms",0) or 0) <= end_window
                and str(obj.get("team") or "") == enemy_team
            ]
            lost_towers = [
                tower for tower in tower_events
                if start_ms <= int(tower.get("time_ms",0) or 0) <= end_window
                and str(tower.get("team") or "") == enemy_team
            ]
            if delta > -900 and not lost_objectives and not lost_towers:
                continue
            severity = max(0, -delta) + len(lost_objectives) * 900 + len(lost_towers) * 650
            rows.append({
                "fight": fight, "before": before_gap, "after": after_gap, "delta": delta,
                "objectives": lost_objectives, "towers": lost_towers, "severity": severity,
            })
        rows.sort(key=lambda item: item["severity"], reverse=True)
        return rows[:limit]

    def analysis_objective_points(role_name, limit=3):
        rows = []
        obj_name_map = {"DRAGON":"드래곤", "RIFT_HERALD":"전령", "BARON":"바론", "ELDER_DRAGON":"장로"}
        for obj in sorted(objective_events, key=lambda item: int(item.get("time_ms",0) or 0)):
            obj_ms = int(obj.get("time_ms",0) or 0)
            nearby = min(
                (fight for fight in teamfights if fight.get("target_involved") and abs(int(fight.get("start_ms",0) or 0)-obj_ms) <= 75_000),
                key=lambda fight: abs(int(fight.get("start_ms",0) or 0)-obj_ms),
                default=None,
            )
            if not nearby:
                continue
            before = series_before_ms(int(nearby.get("start_ms",0) or 0))
            after = series_after_ms(int(nearby.get("end_ms",0) or 0) + 120_000)
            if not before or not after:
                continue
            before_gap = _team_gold_gap_from_series(before, target_team)
            after_gap = _team_gold_gap_from_series(after, target_team)
            name = obj_name_map.get(str(obj.get("name") or "").upper(), str(obj.get("name") or "오브젝트"))
            rows.append({
                "obj": obj, "fight": nearby, "name": name,
                "before": before_gap, "after": after_gap, "delta": after_gap-before_gap,
            })
        rows.sort(key=lambda item: abs(item["delta"]), reverse=True)
        return rows[:limit]

    role_page_labels = {
        key: ("🌱 초반", "⚔️ 주요 교전", "🧠 승부 포인트", "📋 총정리")
        for key in ("탑", "정글", "미드", "원딜", "서폿")
    }
    page_labels = role_page_labels.get(role, ("🌱 성장", "🧭 운영", "⚔️ 교전", "📋 총정리"))
    
    analysis_matchup = resolve_analysis_matchup(
        participant,
        participants,
        rofl_rows,
        player_series,
        opponent_id=opponent_id,
        opponent_identity=opponent_identity,
        opponent_final_row=opponent_final_row,
    )
    analysis_context = make_match_analysis_context(
        guild=interaction.guild,
        gid=str(interaction.guild_id or ""),
        player_name=str(player_name or ""),
        role=str(role or "미지정"),
        champion=str(champion or ""),
        opponent_champion=str(analysis_matchup["opponent_champion_name"] or "상대 챔피언"),
        participant_id=analysis_matchup["participant_id"],
        opponent_id=int(analysis_matchup["opponent_id"] or 0),
        target_team=analysis_matchup["target_team"],
        enemy_team=analysis_matchup["enemy_team"],
        rofl_rows=rofl_rows,
        checkpoint_analysis=checkpoint_analysis,
        player_series=player_series,
        opponent_final_row=analysis_matchup["opponent_final_row"],
        kill_events=kill_events,
        objective_events=objective_events,
        tower_events=tower_events,
        quest_events=quest_events,
        patch_label=patch_label,
        patch_display_label=patch_display_label,
        pages=[early_embed, operation_embed, combat_embed, weakness_embed],
        page_labels=page_labels,
    )
    analysis_context.values.update({
        "_team_gold_gap_from_series": _team_gold_gap_from_series,
        "champion": champion,
        "format_game_time": format_game_time,
        "gold_gap_delta_text": gold_gap_delta_text,
        "gold_gap_state": gold_gap_state,
        "opponent_champion_name": opponent_champion_name,
        "opponent_id": opponent_id,
        "participant_id": participant_id,
        "patch_label": patch_label,
        "quest_time_ms": quest_time_ms,
        "series_after_ms": series_after_ms,
        "series_before_ms": series_before_ms,
        "target_team": target_team,
        "top_enemy_outer_tower": top_enemy_outer_tower,
        "top_fight_line": top_fight_line,
        "top_lane_2v2_fights": top_lane_2v2_fights,
        "top_post_tower_objective_lines": top_post_tower_objective_lines,
        "top_prequest_swings": top_prequest_swings,
        "top_quest_compare_text": top_quest_compare_text,
        "top_side_operation_text": top_side_operation_text,
        "top_swing_text": top_swing_text,
        "enemy_team": enemy_team,
        "first_outer_tower_time_ms": first_outer_tower_time_ms,
        "gap_change_text": gap_change_text,
        "jungle_early_growth_story": jungle_early_growth_story,
        "jungle_gold_gap_at": jungle_gold_gap_at,
        "jungle_growth_line": jungle_growth_line,
        "jungle_growth_swings": jungle_growth_swings,
        "jungle_intervention_line": jungle_intervention_line,
        "jungle_intervention_summary": jungle_intervention_summary,
        "jungle_interventions": jungle_interventions,
        "objective_damage_share": objective_damage_share,
        "objective_events": objective_events,
        "objective_fight_analysis": objective_fight_analysis,
        "opponent_jungle_champion_name": opponent_jungle_champion_name,
        "raw_gold_compare_delta": raw_gold_compare_delta,
        "role_matchup_header": role_matchup_header,
        "add_compact_impact_highlights": add_compact_impact_highlights,
        "add_fight_log": add_fight_log,
        "add_lane_tactical_field": add_lane_tactical_field,
        "fight_deaths": fight_deaths,
        "fight_losses": fight_losses,
        "fight_wins": fight_wins,
        "involved_fights": involved_fights,
        "avg_measured_dpm": avg_measured_dpm,
        "combat_metric_series": combat_metric_series,
        "final_row": final_row,
        "gold_swing_text": gold_swing_text,
        "measured_dpm_rows": measured_dpm_rows,
        "rofl_combat_checkpoint": rofl_combat_checkpoint,
        "add_impact_highlights": add_impact_highlights,
        "add_tower_timeline": add_tower_timeline,
        "early": early,
        "fight_survival_rate": fight_survival_rate,
        "fight_takedowns": fight_takedowns,
        "interval_participation": interval_participation,
        "level_from_xp": level_from_xp,
        "max_game_minute": max_game_minute,
        "opponent_final_row": opponent_final_row,
        "player_name": player_name,
        "role": role,
        "stats_for_row": stats_for_row,
        "analysis_early_cutoff": analysis_early_cutoff,
        "analysis_early_cutoff_text": analysis_early_cutoff_text,
        "analysis_early_summary": analysis_early_summary,
        "analysis_early_detail": analysis_early_detail,
        "analysis_key_fights": analysis_key_fights,
        "analysis_fight_line": analysis_fight_line,
        "analysis_swing_points": analysis_swing_points,
        "analysis_death_mistakes": analysis_death_mistakes,
        "analysis_objective_points": analysis_objective_points,
    })
    role_builder = {
        "탑": build_top_analysis_pages,
        "정글": build_jungle_analysis_pages,
        "미드": build_mid_analysis_pages,
        "원딜": build_adc_analysis_pages,
        "서폿": build_support_analysis_pages,
    }.get(role, lambda ctx: list(ctx.pages))
    pages = role_builder(analysis_context)

    # Use one stable report title across every role/page. Individual page
    # meaning stays in the buttons and fields, so the header no longer
    # jumps around while paging through the report.
    report_title = f"{player_name} 리포트 - {patch_display_label} 패치"
    for _report_embed in (early_embed, operation_embed, combat_embed, weakness_embed):
        _report_embed.title = report_title
    
    analysis_context.pages = pages
    return analysis_context


def register_replay_commands(runtime):
    """Register replay commands and return callbacks used by the main bot."""
    globals().update(runtime)
    detail_save_processing = set()

    def _sync_runtime():
        globals().update(runtime)

    def build_detail_stat_embed(title, rows, empty_message):
        embed = discord.Embed(title=title, color=0x3498db)
        if not rows:
            embed.description = empty_message
            return embed
    
        lines = [match_stats.format_stat_line(row) for row in rows[:15]]
        embed.description = "\n".join(lines)
        return embed
    
    def build_champion_simple_stats_embed(title, rows, empty_message, *, page=1, page_size=10):
        embed = discord.Embed(title=title, color=0x3498db)
        if not rows:
            embed.description = empty_message
            return embed
    
        lines = []
        total_pages = max(1, (len(rows) + page_size - 1) // page_size)
        page = max(1, min(int(page or 1), total_pages))
        page_rows = rows[(page - 1) * page_size:page * page_size]
        start_rank = (page - 1) * page_size + 1
        for idx, row in enumerate(page_rows, start_rank):
            lines.append(
                f"`{idx:>2}` **{row['label']}** · "
                f"{row['games']}전 {row['wins']}승 {row['losses']}패 · "
                f"승률 **{row['winrate']:.1f}%**"
            )
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"{page}/{total_pages}페이지 · 상세스탯 저장 기록 기준 · 판수순 정렬")
        return embed
    
    def format_personal_champion_line(idx, row, *, include_dpm=False, hide_dpm=False):
        record = f"{row['games']}전 {row['wins']}승 {row['losses']}패"
        parts = [
            f"`{idx:>2}` **{row['label']}**",
            f"`{record}`",
            f"승률 **{row['winrate']:.1f}%**",
            f"KDA **{row['kda']:.1f}**",
        ]
        if include_dpm and not hide_dpm:
            parts.append(f"분당 피해량 **{row['dpm']:.0f}**")
        mvp_count = int(row.get("mvp_count", 0) or 0)
        ace_count = int(row.get("ace_count", 0) or 0)
        if mvp_count:
            parts.append(f"MVP **{mvp_count}회**")
        if ace_count:
            parts.append(f"ACE **{ace_count}회**")
        return " · ".join(parts)
    
    def build_champion_personal_stats_embed(title, rows, empty_message, *, include_dpm=False, role=None, page=1, page_size=10):
        embed = discord.Embed(title=title, color=0xf1c40f if not include_dpm else 0x3498db)
        if not rows:
            embed.description = empty_message
            return embed
    
        total_pages = max(1, (len(rows) + page_size - 1) // page_size)
        page = max(1, min(int(page or 1), total_pages))
        page_rows = rows[(page - 1) * page_size:page * page_size]
        start_rank = (page - 1) * page_size + 1
        lines = [
            format_personal_champion_line(
                idx,
                row,
                include_dpm=include_dpm,
                hide_dpm=(role == "서폿" or get_row_primary_role(row) == "서폿"),
            )
            for idx, row in enumerate(page_rows, start_rank)
        ]
        embed.description = "\n\n".join(lines)
        footer_note = "상세스탯 저장 기록 기준 · 판수순 정렬"
        if role == "서폿":
            footer_note += " · 서폿 분당 피해량 제외"
        embed.set_footer(text=f"{page}/{total_pages}페이지 · {footer_note}")
        return embed
    
    def format_compact_detail_line(row):
        return (
            f"{row['games']}전 {row['wins']}승 {row['losses']}패 "
            f"({row['winrate']:.1f}%) · KDA {row['kda']:.1f} · "
            f"분당 피해량 {row['dpm']:.0f} · 킬 관여율 {row['avg_kp']:.1f}%"
        )
    
    def sort_champion_summary_rows(rows):
        return sorted(
            rows,
            key=lambda row: (
                int(row.get("games", 0) or 0),
                float(row.get("winrate", 0) or 0),
                int(row.get("wins", 0) or 0),
                float(row.get("kda", 0) or 0),
            ),
            reverse=True,
        )
    
    def sort_champion_winrate_rows(rows):
        return sorted(
            rows,
            key=lambda row: (
                float(row.get("winrate", 0) or 0),
                int(row.get("games", 0) or 0),
                int(row.get("wins", 0) or 0),
                float(row.get("kda", 0) or 0),
            ),
            reverse=True,
        )
    
    def normalize_detail_group_label(group_key, label):
        text = str(label or "미지정").strip()
        if group_key == "champion":
            compact = "".join(text.split()).lower()
            return compact or "미지정"
        return text or "미지정"
    
    def prefer_detail_display_label(current, candidate):
        current = str(current or "").strip()
        candidate = str(candidate or "").strip()
        if not candidate:
            return current or "미지정"
        if not current or current == "미지정":
            return candidate
        if " " not in current and " " in candidate:
            return candidate
        return current
    
    def get_row_primary_role(row):
        role_counts = row.get("_role_counts") or {}
        if not role_counts:
            return None
        return max(role_counts.items(), key=lambda item: item[1])[0]
    
    def format_champion_summary_line(row, *, compact=False, hide_dpm=False):
        mvp_count = int(row.get("mvp_count", 0) or 0)
        ace_count = int(row.get("ace_count", 0) or 0)
    
        detail_parts = [f"KDA **{row['kda']:.1f}**"]
        if not hide_dpm:
            detail_parts.append(f"DPM **{row['dpm']:.0f}**")
        if mvp_count:
            detail_parts.append(f"🥇 **{mvp_count}회**")
        if ace_count:
            detail_parts.append(f"🛡️ **{ace_count}회**")
    
        return (
            f"**{row['label']}** · {row['games']}전 {row['wins']}승 · **{row['winrate']:.1f}%**\n"
            f"　{' · '.join(detail_parts)}"
        )
    
    def format_detail_summary_header(row, *, role=None, guild=None):
        games = int(row.get("games", 0) or 0)
        record = f"{games}전 {row['wins']}승 {row['losses']}패"
        winrate = f"{row['winrate']:.1f}%"
        if role:
            role_emoji = get_role_display_marker(role, guild)
            return f"{role_emoji} **{role}**  `{record}`  승률 **{winrate}**"
        return f"📌 **종합 전적**  `{record}`  승률 **{winrate}**"
    
    def aggregate_detail_entries(guild_data, *, user_id=None, role=None, group_key=None):
        if group_key:
            buckets = {}
        else:
            bucket = match_stats.new_bucket(str(user_id or "summary"))
    
        for entry in match_stats.iter_entries(guild_data, user_id=str(user_id) if user_id else None):
            if role and entry.get("role") != role:
                continue
            if group_key:
                label = str(entry.get(group_key) or "미지정")
                bucket_key = normalize_detail_group_label(group_key, label)
                item = buckets.setdefault(bucket_key, match_stats.new_bucket(label))
                item["label"] = prefer_detail_display_label(item.get("label"), label)
                if group_key == "champion":
                    role_counts = item.setdefault("_role_counts", {})
                    entry_role = str(entry.get("role") or "미지정")
                    role_counts[entry_role] = role_counts.get(entry_role, 0) + 1
                match_stats.add_to_bucket(item, entry)
            else:
                match_stats.add_to_bucket(bucket, entry)
    
        if group_key:
            rows = [match_stats.finalize_bucket(item) for item in buckets.values()]
            award_counts = award_counts_for_detail_filter(guild_data, user_id=user_id, role=role, group_key=group_key)
            for row in rows:
                bucket_key = normalize_detail_group_label(group_key, row["label"])
                counts = award_counts.get(bucket_key, {})
                row["mvp_count"] = counts.get("mvp_count", 0)
                row["ace_count"] = counts.get("ace_count", 0)
            return rows
    
        if bucket["games"] == 0:
            return None
        counts = award_counts_for_detail_filter(guild_data, user_id=user_id, role=role).get(str(user_id), {})
        bucket["mvp_count"] = counts.get("mvp_count", 0)
        bucket["ace_count"] = counts.get("ace_count", 0)
        return match_stats.finalize_bucket(bucket)
    
    def award_counts_for_detail_filter(guild_data, *, user_id=None, role=None, group_key=None):
        counts = {}
        for match_id, match_entries in match_stats.get_store(guild_data).items():
            try:
                awards = match_stats.score_match_awards(guild_data, match_id)
            except Exception:
                logger.exception("상세 통계 수상 집계 제외 경기: %s", match_id)
                continue
            for award_key, count_key in (("mvp", "mvp_count"), ("ace", "ace_count")):
                award = awards.get(award_key)
                if not award:
                    continue
                if user_id and str(award.get("user_id")) != str(user_id):
                    continue
                if role and award.get("role") != role:
                    continue
                label = str(award.get(group_key) or "미지정") if group_key else str(award.get("user_id"))
                bucket_key = normalize_detail_group_label(group_key, label) if group_key else label
                item = counts.setdefault(bucket_key, {"mvp_count": 0, "ace_count": 0})
                item[count_key] += 1
        return counts
    
    def build_detail_summary_embed(title, row, champion_rows, *, role=None, guild=None):
        embed = discord.Embed(title=title, color=0x2f80ed)
        if not row:
            embed.description = f"📭 아직 `{role}` 라인 상세 스탯이 없습니다." if role else "📭 아직 기록된 상세 스탯이 없습니다."
            return embed
    
        embed.description = format_detail_summary_header(row, role=role, guild=guild)
    
        # 숫자를 가로로 몰아넣지 않고, 한 번에 훑을 수 있는 세로형 요약으로 표시.
        performance_lines = [
            f"**KDA**　{row['kda']:.1f}",
            f"**분당 피해량**　{row['dpm']:.0f}",
            f"**킬 관여율**　{row['avg_kp']:.1f}%",
        ]
        embed.add_field(
            name="⚔️ 평균 퍼포먼스",
            value="\n".join(performance_lines),
            inline=False,
        )
    
        champion_rows = sort_champion_summary_rows(champion_rows)
        limit = 5 if role else 3
        champion_title = f"💠 {role} 챔피언" if role else "💠 MOST 챔피언"
        embed.add_field(
            name=champion_title,
            value="\n\n".join(
                format_champion_summary_line(
                    item,
                    hide_dpm=(role == "서폿" or get_row_primary_role(item) == "서폿"),
                )
                for item in champion_rows[:limit]
            ) if champion_rows else "기록 없음",
            inline=False,
        )
    
        mvp_count = int(row.get("mvp_count", 0) or 0)
        ace_count = int(row.get("ace_count", 0) or 0)
        award_count = mvp_count + ace_count
        award_rate = (award_count / row["games"] * 100) if row.get("games", 0) else 0.0
        mvp_points = mvp_count * 100 + ace_count * 50
    
        embed.add_field(
            name="🏆 MVP 기록",
            value=(
                f"🥇 MVP **{mvp_count}회**\n"
                f"🛡️ ACE **{ace_count}회**\n"
                f"수상률 **{award_rate:.1f}%**\n"
                f"MVP 포인트 **{mvp_points}P**"
            ),
            inline=False,
        )
        return embed
    
    def normalize_record_detail_view(value):
        text = str(value or "").strip().lower().replace(" ", "")
        if not text:
            return None
        if text in ("챔피언", "챔", "champion", "champ"):
            return ("champion", None)
        if text in ("라인", "포지션", "role", "roles"):
            return ("roles", None)
        role = normalize_role_name(text)
        if role:
            return ("role", role)
        return None
    
    def build_record_detail_embed(guild, gid, uid, user_info, detail_view):
        guild_data = bot.user_data.setdefault(gid, {})
        lol_name = user_info.get("lol_name", get_member_display_name(guild, gid, uid))
        view_type, role = detail_view
    
        if view_type == "champion":
            rows = sort_champion_summary_rows(match_stats.aggregate_by(guild_data, "champion", user_id=uid))
            embed = build_detail_stat_embed(
                f"🧾 {lol_name} 챔피언 상세 전적",
                rows,
                "📭 아직 저장된 챔피언 상세 스탯이 없습니다."
            )
            embed.set_footer(text="승률/KDA/분당 피해량/킬 관여율/MVP/ACE는 상세스탯 저장 기록 기준입니다.")
            return embed
    
        if view_type == "roles":
            rows = match_stats.sort_rows(match_stats.aggregate_by(guild_data, "role", user_id=uid), key="games")
            embed = build_detail_stat_embed(
                f"🧭 {lol_name} 라인 상세 전적",
                rows,
                "📭 아직 저장된 라인 상세 스탯이 없습니다."
            )
            embed.set_footer(text="승률/KDA/분당 피해량/킬 관여율/MVP/ACE는 상세스탯 저장 기록 기준입니다.")
            return embed
    
        rows = match_stats.aggregate_by(guild_data, "role", user_id=uid)
        row = next((item for item in rows if item.get("label") == role), None)
        embed = discord.Embed(title=f"🧭 {lol_name} {role} 상세 전적", color=0x3498db)
        if not row or row.get("games", 0) <= 0:
            embed.description = f"📭 아직 `{role}` 라인 상세 스탯이 없습니다."
            return embed
        embed.description = match_stats.format_stat_line(row, include_label=False)
        embed.add_field(
            name="평균 기록",
            value=(
                f"K/D/A **{row['avg_kills']:.1f}/{row['avg_deaths']:.1f}/{row['avg_assists']:.1f}**\n"
                f"KDA **{row['kda']:.1f}** | 분당 피해량 **{row['dpm']:.0f}** | 킬 관여율 **{row['avg_kp']:.1f}%**"
            ),
            inline=False
        )
        embed.set_footer(text="MVP/ACE는 포지션별 AI 점수와 맞라인 초과성과 보정 기준입니다.")
        return embed
    
    def get_opponent_player_record(match_record, player):
        if not match_record or not player:
            return None
        role = player.get("role")
        team = player.get("team")
        for other in match_record.get("players", []):
            if other.get("role") == role and other.get("team") != team:
                return other
        return None
    
    def format_award_line(guild, gid, award):
        if not award:
            return "기록 없음"
        name = get_member_display_name(guild, gid, award.get("user_id"))
        score = award.get("display_score", award.get("expectation_score", award.get("score")))
        try:
            score_text = f" · AI {float(score):.1f}점"
        except (TypeError, ValueError):
            score_text = ""
        return (
            f"**{name}** `{award.get('role')}` {award.get('champion')}\n"
            f"KDA {award.get('kda'):.1f}{score_text}"
        )
    
    def format_award_summary(guild, gid, award):
        if not award:
            return "기록 없음"
        name = get_member_display_name(guild, gid, award.get("user_id"))
        score = award.get("display_score", award.get("expectation_score", award.get("score")))
        try:
            score_text = f" · AI {float(score):.1f}점"
        except (TypeError, ValueError):
            score_text = ""
        return f"**{name}** `{award.get('role')}` {award.get('champion')}{score_text}"
    
    def build_match_awards_embed(guild, gid, match_id):
        guild_data = bot.user_data.setdefault(gid, {})
        awards = match_stats.score_match_awards(guild_data, match_id)
        embed = discord.Embed(title="🏅 경기 상세 MVP / ACE", color=0xf1c40f)
        embed.add_field(name="MVP", value=format_award_line(guild, gid, awards.get("mvp")), inline=False)
        embed.add_field(name="ACE", value=format_award_line(guild, gid, awards.get("ace")), inline=False)
        return embed
    
    def build_detail_stat_analysis_prompt(guild, gid, record):
        player_lines = []
        for player in record.get("players", []):
            uid = str(player.get("user_id"))
            player_lines.append(
                {
                    "user_id": uid,
                    "registered_name": get_member_display_name(guild, gid, uid),
                    "team": player.get("team"),
                    "role": player.get("role"),
                    "result": player.get("result"),
                }
            )
        return (
            "You are extracting League of Legends custom match stats from two screenshots: "
            "one scoreboard screenshot and one champion-damage graph screenshot. "
            "Use the provided lineup as the source of truth for user_id, team, role, and result. "
            "The scoreboard order may not match lane order. Match rows by visible summoner name when possible. "
            "If a name is uncertain, still choose the most likely lineup user and set confidence below 0.7. "
            "Do not invent values that are not visible. Return JSON only.\n\n"
            f"Lineup JSON:\n{json.dumps(player_lines, ensure_ascii=False)}\n\n"
            "Return this exact JSON shape:\n"
            "{\n"
            '  "duration": "MM:SS",\n'
            '  "blue_team_kills": 0,\n'
            '  "red_team_kills": 0,\n'
            '  "entries": [\n'
            "    {\n"
            '      "user_id": "discord user id from lineup",\n'
            '      "screenshot_name": "visible summoner name",\n'
            '      "champion": "champion name if confidently identified, otherwise empty string",\n'
            '      "kills": 0,\n'
            '      "deaths": 0,\n'
            '      "assists": 0,\n'
            '      "cs": 0,\n'
            '      "gold": 0,\n'
            '      "damage": 0,\n'
            '      "confidence": 0.0,\n'
            '      "notes": ""\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )
    
    def extract_response_text(response_json):
        if isinstance(response_json.get("output_text"), str):
            return response_json["output_text"]
        chunks = []
        for item in response_json.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    chunks.append(text)
        return "\n".join(chunks)
    
    def parse_json_object(text):
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end >= start:
            text = text[start:end + 1]
        return json.loads(text)
    
    def call_openai_vision_sync(prompt, image_payloads):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
    
        model = os.getenv("OPENAI_VISION_MODEL", "gpt-5-mini")
        content = [{"type": "input_text", "text": prompt}]
        for payload in image_payloads:
            content.append({
                "type": "input_image",
                "image_url": payload["data_url"],
                "detail": "high",
            })
    
        body = json.dumps({
            "model": model,
            "input": [{"role": "user", "content": content}],
        }).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                response_json = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error {exc.code}: {detail[:500]}") from exc
    
        return parse_json_object(extract_response_text(response_json))
    
    async def attachment_to_data_url(attachment):
        raw = await attachment.read()
        mime = attachment.content_type or "image/png"
        encoded = base64.b64encode(raw).decode("ascii")
        return {"filename": attachment.filename, "data_url": f"data:{mime};base64,{encoded}"}
    
    
    
    class DetailStatConfirmView(discord.ui.View):
        def __init__(self, gid, record, entries, requester_id, retroactive_state=None, tournament_state=None):
            super().__init__(timeout=300)
            self.gid = str(gid)
            self.record = record
            self.entries = entries
            self.requester_id = requester_id
            self.retroactive_state = retroactive_state
            self.tournament_state = tournament_state
            self.confirm_processing = False
            self.confirm_completed = False
            self.retroactive_processing = False
            self.last_final_rating_lines = []
            if not self.retroactive_state:
                for item in list(self.children):
                    if getattr(item, "label", "") in ("전적 소급 반영", "지난 경기 반영"):
                        self.remove_item(item)
    
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if is_match_admin(interaction):
                return True
            await interaction.response.send_message("⚠️ 내전 관리자만 확정할 수 있습니다.", ephemeral=True)
            return False
    
        async def save_detail_entries(self, interaction: discord.Interaction, record=None, entries=None, *, reset_title_batch=True):
            _sync_runtime()
            record = record or self.record
            entries = entries or self.entries
            dependencies = DetailSaveDependencies(
                bot=bot,
                match_stats=match_stats,
                apply_ai_mmr_adjustments_for_record=runtime["apply_ai_mmr_adjustments_for_record"],
                is_already_saved_rofl_detail=is_already_saved_rofl_detail,
                sync_match_duration=sync_match_duration,
                get_entry_missing_fields=get_entry_missing_fields,
                title_checkers=(
                    check_champion_mastery_titles_for_entries,
                    check_detail_award_titles_for_entries,
                    check_zero_death_titles_for_entries,
                    check_penta_kill_titles_for_entries,
                    check_s2_detail_titles_for_entries,
                ),
                sync_registered_member_tier_role=sync_registered_member_tier_role,
                processing_keys=detail_save_processing,
                logger=logger,
                clear_rating_lines=lambda: setattr(self, "last_final_rating_lines", []),
            )
            saved_count, final_rating_lines = await save_replay_detail_entries(
                interaction=interaction,
                gid=self.gid,
                record=record,
                entries=entries,
                reset_title_batch=reset_title_batch,
                dependencies=dependencies,
            )
            self.last_final_rating_lines = final_rating_lines
            return saved_count
    
        @discord.ui.button(label="확정 저장", style=discord.ButtonStyle.success)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            _sync_runtime()
            if self.confirm_completed:
                return await interaction.response.send_message("✅ 상세 스탯이 이미 저장되었습니다.", ephemeral=True)
            if self.confirm_processing:
                return await interaction.response.send_message("⏳ 상세 스탯 저장이 이미 처리 중입니다.", ephemeral=True)
            self.confirm_processing = True
            for item in self.children:
                item.disabled = True
            await interaction.response.defer()
            try:
                record = self.record
                entries = self.entries
                if self.tournament_state:
                    tournament_state = self.tournament_state
                    process_win = runtime.get("win_record")
                    if not callable(process_win):
                        process_win = getattr(process_win, "callback", None)
                    if not callable(process_win):
                        raise RuntimeError("리그전 결과 처리 함수를 찾지 못했습니다.")
                    internal_marker = object()
                    previous_internal = getattr(interaction, "_lucid_internal_match_record", internal_marker)
                    setattr(interaction, "_lucid_internal_match_record", True)
                    try:
                        record = await process_win(
                            interaction,
                            tournament_state["queue_key"],
                            str(tournament_state["match_no"]),
                            tournament_state["winner_text"],
                        )
                    finally:
                        if previous_internal is internal_marker:
                            try:
                                delattr(interaction, "_lucid_internal_match_record")
                            except AttributeError:
                                pass
                        else:
                            setattr(interaction, "_lucid_internal_match_record", previous_internal)
                    if not isinstance(record, dict) or not str(record.get("id") or "").strip():
                        raise RuntimeError("ROFL과 연결할 리그전 경기 기록을 만들지 못했습니다.")
                    entries = [
                        {**entry, "match_id": record["id"]}
                        for entry in entries
                    ]
                    self.record = record
                    self.entries = entries
                    self.tournament_state = None
                saved_count = await self.save_detail_entries(
                    interaction,
                    record=record,
                    entries=entries,
                )
                self.confirm_completed = True
                guild_data = bot.user_data.setdefault(self.gid, {})
                embed = build_match_awards_embed(interaction.guild, self.gid, self.record.get("id"))
                embed.description = f"상세 스탯 **{saved_count}명** 저장 완료"
                if self.last_final_rating_lines:
                    embed.add_field(name="📊 최종 레이팅", value="\n".join(self.last_final_rating_lines[:10]), inline=False)
                missing_lines = format_missing_detail_lines(interaction.guild, self.gid, self.record, guild_data)
                if missing_lines:
                    embed.add_field(
                        name="🧩 누락 데이터",
                        value="\n".join(missing_lines[:5]) + "\n\n누락된 상세기록은 `/리플레이기록`으로 ROFL 파일을 다시 올려 보완할 수 있습니다.",
                        inline=False
                    )
                await interaction.edit_original_response(embed=embed, view=self)
            except Exception as exc:
                logger.exception("ROFL/detail stat confirm failed")
                await interaction.followup.send(f"⚠️ 상세 스탯 저장 실패: `{str(exc)[:900]}`", ephemeral=True)
            finally:
                self.confirm_processing = False
                await flush_title_batch(interaction, self.gid)
    
        @discord.ui.button(label="지난 경기 반영", style=discord.ButtonStyle.primary)
        async def retroactive_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            _sync_runtime()
            if not self.retroactive_state:
                return await interaction.response.send_message("⚠️ 지난 경기로 반영할 수 없는 ROFL입니다.", ephemeral=True)
            if self.retroactive_processing:
                return await interaction.response.send_message("⏳ 지난 경기 반영이 이미 처리 중입니다.", ephemeral=True)
    
            self.retroactive_processing = True
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(content="⏳ ROFL 경기 전적을 반영하는 중입니다...", embed=None, view=self)
    
            game_state = self.retroactive_state.get("game_state")
            winner = self.retroactive_state.get("winner")
            if bot.title_batch is None:
                bot.title_batch = {}
            bot.title_batch[self.gid] = []
            try:
                await process_classic_win(interaction, self.gid, "retro", winner, False, game_state, retroactive=True)
                self.retroactive_state = None
                match_id = bot.history.get(self.gid, {}).get("retro", {}).get("match_id")
                record = match_stats.find_match_record(bot.user_data.setdefault(self.gid, {}), match_id)
                if not record:
                    raise RuntimeError("소급 경기 기록을 찾지 못했습니다.")
    
                entries = []
                for entry in self.entries:
                    new_entry = dict(entry)
                    new_entry["match_id"] = match_id
                    entries.append(new_entry)
                saved_count = await self.save_detail_entries(interaction, record=record, entries=entries, reset_title_batch=False)
    
                embed = build_match_awards_embed(interaction.guild, self.gid, match_id)
                embed.description = (
                    f"ROFL 경기 전적/MMR 반영 완료\n"
                    f"상세 스탯 **{saved_count}명** 저장 완료"
                )
                if self.last_final_rating_lines:
                    embed.add_field(name="📊 최종 레이팅", value="\n".join(self.last_final_rating_lines[:10]), inline=False)
                await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except Exception as exc:
                logger.exception("ROFL retroactive confirm failed")
                await interaction.followup.send(f"⚠️ ROFL 경기 반영 실패: `{str(exc)[:900]}`", ephemeral=True)
            finally:
                self.retroactive_processing = False
                await flush_title_batch(interaction, self.gid)
    
        @discord.ui.button(label="취소", style=discord.ButtonStyle.danger)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(content="상세 스탯 저장을 취소했습니다.", embed=None, view=self)
    
    async def detail_stat_input(
        interaction: discord.Interaction,
        유저: discord.Member,
        순번: app_commands.Range[int, 1, 50] = 1,
        챔피언: str = "",
        킬: app_commands.Range[int, 0, 99] = None,
        데스: app_commands.Range[int, 0, 99] = None,
        어시: app_commands.Range[int, 0, 99] = None,
        딜량: app_commands.Range[int, 0, 999999] = None,
        경기시간: str = "",
        스샷소환사명: str = "",
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 상세 스탯을 수정할 수 있습니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
        if len(records) < 순번:
            return await interaction.response.send_message(
                f"⚠️ 확인 가능한 경기 기록은 {len(records)}개입니다.",
                ephemeral=True
            )
    
        record = records[순번 - 1]
        uid = str(유저.id)
        player = match_stats.find_player_record(record, uid)
        if not player:
            return await interaction.response.send_message(
                "⚠️ 해당 유저는 선택한 경기 기록의 참가자로 확인되지 않습니다.",
                ephemeral=True
            )
        opponent = get_opponent_player_record(record, player)
    
        guild_data = bot.user_data.setdefault(gid, {})
        existing = match_stats.get_store(guild_data).get(str(record.get("id")), {}).get(uid, {})
        required_missing = []
        if not (챔피언 or existing.get("champion")):
            required_missing.append("챔피언")
        if 킬 is None and "kills" not in existing:
            required_missing.append("킬")
        if 데스 is None and "deaths" not in existing:
            required_missing.append("데스")
        if 어시 is None and "assists" not in existing:
            required_missing.append("어시")
        if 딜량 is None and "damage" not in existing:
            required_missing.append("딜량")
        duration_seconds = match_stats.parse_duration_seconds(경기시간) if 경기시간 else int(existing.get("duration_seconds", 0) or 0)
        if duration_seconds <= 0:
            required_missing.append("경기시간")
        if required_missing:
            return await interaction.response.send_message(
                f"⚠️ 기존 상세스탯이 없어 `{', '.join(required_missing)}` 값이 필요합니다.",
                ephemeral=True
            )
    
        entry = match_stats.build_entry(
            match_id=record.get("id"),
            user_id=uid,
            champion=챔피언 or existing.get("champion", ""),
            role=player.get("role", "미지정"),
            team=player.get("team", "unknown"),
            result=player.get("result", "unknown"),
            kills=킬 if 킬 is not None else int(existing.get("kills", 0)),
            deaths=데스 if 데스 is not None else int(existing.get("deaths", 0)),
            assists=어시 if 어시 is not None else int(existing.get("assists", 0)),
            cs=int(existing.get("cs", 0) or 0),
            gold=int(existing.get("gold", 0) or 0),
            damage=딜량 if 딜량 is not None else int(existing.get("damage", 0)),
            duration_seconds=duration_seconds,
            team_kills=0,
            before_mmr=player.get("before_mmr", 0),
            opponent_mmr=opponent.get("before_mmr", 0) if opponent else 0,
            screenshot_name=스샷소환사명 or existing.get("screenshot_name", ""),
            source="manual",
            double_kills=int(existing.get("double_kills", 0) or 0),
            triple_kills=int(existing.get("triple_kills", 0) or 0),
            quadra_kills=int(existing.get("quadra_kills", 0) or 0),
            penta_kills=int(existing.get("penta_kills", 0) or 0),
            largest_multi_kill=int(existing.get("largest_multi_kill", 0) or 0),
            rofl_stats=existing.get("rofl_stats") or {},
        )
        if isinstance(existing.get("objective_steal"), dict):
            entry["objective_steal"] = dict(existing.get("objective_steal"))
        saved = match_stats.upsert_entry(guild_data, entry)
        if 경기시간:
            sync_match_duration(guild_data, record, duration_seconds)
            saved = match_stats.get_store(guild_data).get(str(record.get("id")), {}).get(uid, saved)
        final_rating_lines = apply_ai_mmr_adjustments_for_record(gid, record)
        if final_rating_lines:
            for player in record.get("players", []) or []:
                player_uid = str(player.get("user_id"))
                if player_uid in guild_data:
                    await sync_registered_member_tier_role(interaction.guild, gid, player_uid)
        await check_champion_mastery_titles(interaction, gid, uid)
        await check_detail_award_titles_for_match(interaction, gid, record.get("id"))
        await check_zero_death_titles(interaction, gid, uid)
        await check_s2_detail_titles(interaction, gid, uid)
        bot.save_lucid_data(gid)
    
        embed = discord.Embed(
            title="🛠️ 상세 스탯 수정 완료",
            description=(
                f"경기: **최근 {순번}번째 경기** (`{record.get('id')}`)\n"
                f"대상: {유저.mention} / 라인: **{saved.get('role')}** / 챔피언: **{saved.get('champion')}**\n"
                f"KDA: **{saved['kills']}/{saved['deaths']}/{saved['assists']}** | 딜량 **{saved['damage']:,}** | 시간 **{saved['duration']}**\n"
                f"평균KDA **{saved['kda']:.1f}** | 분당 피해량 **{saved['dpm']:.0f}** | 킬 관여율 **{saved['kill_participation']:.1f}%**"
            ),
            color=0x2ecc71
        )
        if 스샷소환사명:
            embed.add_field(name="스샷 소환사명", value=스샷소환사명, inline=False)
        awards = match_stats.score_match_awards(guild_data, record.get("id"))
        if len(awards.get("scores", [])) >= 2:
            embed.add_field(name="MVP", value=format_award_line(interaction.guild, gid, awards.get("mvp")), inline=True)
            embed.add_field(name="ACE", value=format_award_line(interaction.guild, gid, awards.get("ace")), inline=True)
        await interaction.response.send_message(embed=embed)
    
    
    def get_scoreboard_row_player_map(record, shooter_id=None):
        players = list(record.get("players", []) if record else [])
        row_map = {}
        warnings = []
        shooter_id = str(shooter_id) if shooter_id else None
    
        has_blue_red = any(player.get("team") in ("blue", "red") for player in players)
        if has_blue_red:
            team_order = [("blue", 0), ("red", 5)]
            shooter_team = None
            if shooter_id:
                shooter_record = next((player for player in players if str(player.get("user_id")) == shooter_id), None)
                shooter_team = shooter_record.get("team") if shooter_record else None
            if shooter_team == "red":
                team_order = [("red", 0), ("blue", 5)]
                warnings.append("촬영자가 레드팀이라 스샷의 1번 팀을 레드팀으로 보정했습니다.")
            elif shooter_team == "blue":
                warnings.append("촬영자가 블루팀이라 스샷의 1번 팀을 블루팀으로 매칭했습니다.")
    
            for team, offset in team_order:
                team_players = [player for player in players if player.get("team") == team]
                role_order = list(ROLES)
                shooter = next((player for player in team_players if str(player.get("user_id")) == shooter_id), None)
                if shooter and shooter.get("role") in ROLES:
                    shooter_role = shooter.get("role")
                    role_order = [shooter_role] + [role for role in ROLES if role != shooter_role]
                    warnings.append(f"{team}팀: 촬영자 `{shooter_role}` 기준으로 줄 순서를 보정했습니다.")
                used_ids = set()
                for role_index, role in enumerate(role_order, 1):
                    row = offset + role_index
                    player = next(
                        (
                            item for item in team_players
                            if item.get("role") == role and str(item.get("user_id")) not in used_ids
                        ),
                        None,
                    )
                    if not player:
                        player = next(
                            (
                                item for item in team_players
                                if str(item.get("user_id")) not in used_ids
                            ),
                            None,
                        )
                        if player:
                            warnings.append(f"{row}줄: 라인 순서 매칭 불확실")
                    if player:
                        row_map[row] = player
                        used_ids.add(str(player.get("user_id")))
        else:
            for row, player in enumerate(players[:10], 1):
                row_map[row] = player
            warnings.append("블루/레드 팀 정보가 없어 경기 기록 순서대로 매칭했습니다.")
    
        missing_rows = [str(row) for row in range(1, 11) if row not in row_map]
        if missing_rows:
            warnings.append(f"참가자 매칭 누락 줄: {', '.join(missing_rows)}")
        return row_map, warnings
    
    _ROFL_CHAMPION_MAP = None
    _ROFL_CHAMPION_MAP_LOADED = False
    MAX_ROFL_UPLOAD_BYTES = 64 * 1024 * 1024
    # ponytail: 한 번에 하나만 분석해 timeout 뒤 남은 worker가 누적되지 않게 한다.
    _ROFL_ANALYSIS_WORKER_LOCK = threading.Lock()
    
    
    def validate_rofl_upload_size(attachment, raw=None):
        size = len(raw) if raw is not None else int(getattr(attachment, "size", 0) or 0)
        if size > MAX_ROFL_UPLOAD_BYTES:
            raise ValueError(f"ROFL 파일은 {MAX_ROFL_UPLOAD_BYTES // (1024 * 1024)}MB 이하만 분석할 수 있습니다.")
    
    
    def run_rofl_analysis_once(func, *args):
        if not _ROFL_ANALYSIS_WORKER_LOCK.acquire(blocking=False):
            raise RuntimeError("이전 ROFL 경기분석 작업이 아직 종료되지 않았습니다. 잠시 후 다시 시도해주세요.")
        try:
            return func(*args)
        finally:
            _ROFL_ANALYSIS_WORKER_LOCK.release()
    
    def get_rofl_champion_map():
        if runtime.get("_ROFL_CHAMPION_MAP_LOADED"):
            return runtime.get("_ROFL_CHAMPION_MAP")
        try:
            runtime["_ROFL_CHAMPION_MAP"] = rofl.load_ko_champion_map()
        except Exception as exc:
            logger.warning("ROFL champion map load failed: %s", exc)
            runtime["_ROFL_CHAMPION_MAP"] = None
            return None
        runtime["_ROFL_CHAMPION_MAP_LOADED"] = True
        return runtime["_ROFL_CHAMPION_MAP"]
    
    def normalize_rofl_match_name(value):
        text = str(value or "").strip().lower()
        text = re.sub(r"[\s\u200b\u200c\u200d]+", "", text)
        text = text.replace("＃", "#")
        return text
    
    def rofl_name_variants(value):
        full = normalize_rofl_match_name(value)
        if not full:
            return set()
        variants = {full}
        if "#" in full:
            variants.add(full.split("#", 1)[0])
        return variants
    
    def resolve_rofl_input_riot_id(rofl_rows, value):
        """Resolve a typed Riot name against the ROFL file itself.
    
        `name#tag` requires an exact match. A bare `name` is accepted when it
        identifies exactly one participant in the replay. This keeps both ROFL
        analysis commands convenient without guessing when duplicate game names
        with different tags are present.
        """
        target = normalize_rofl_match_name(value)
        if not target:
            return None, []
        candidates = []
        for row in rofl_rows or []:
            riot_id = str(row.get("summoner_name") or "").strip()
            normalized = normalize_rofl_match_name(riot_id)
            if not normalized:
                continue
            if "#" in target:
                matched = normalized == target
            else:
                matched = normalized.split("#", 1)[0] == target
            if matched:
                candidates.append(riot_id)
        # De-duplicate while preserving replay order.
        candidates = list(dict.fromkeys(candidates))
        if len(candidates) == 1:
            return candidates[0], candidates
        return None, candidates
    
    def get_record_player_name_variants(gid, player, guild=None):
        uid = str(player.get("user_id", ""))
        variants = set()
        values = [
            player.get("name"),
            get_saved_lol_name(gid, uid, ""),
            get_member_display_name(guild, gid, uid) if guild else "",
        ]
        values.extend(get_saved_lol_account_names(gid, uid))
        for value in values:
            variants.update(rofl_name_variants(value))
        return variants
    
    def match_rofl_rows_to_record(guild, gid, record, rofl_rows):
        players = list(record.get("players", []) if record else [])
        player_variants = {
            str(player.get("user_id")): get_record_player_name_variants(gid, player, guild)
            for player in players
        }
        used_ids = set()
        matches = []
        warnings = []
    
        for row in rofl_rows:
            row_name = row.get("summoner_name") or ""
            row_variants = rofl_name_variants(row_name)
            matched_player = None
    
            for player in players:
                uid = str(player.get("user_id"))
                if uid in used_ids:
                    continue
                if row_variants & player_variants.get(uid, set()):
                    matched_player = player
                    break
    
            if not matched_player and row_variants:
                best_player = None
                best_score = 0.0
                row_key = next(iter(row_variants))
                for player in players:
                    uid = str(player.get("user_id"))
                    if uid in used_ids:
                        continue
                    for candidate in player_variants.get(uid, set()):
                        score = difflib.SequenceMatcher(None, row_key, candidate).ratio()
                        if score > best_score:
                            best_score = score
                            best_player = player
                if best_player and best_score >= 0.78:
                    matched_player = best_player
                    warnings.append(
                        f"`{row_name}` → `{matched_player.get('name', matched_player.get('user_id'))}` 유사도 매칭({best_score:.2f})"
                    )
    
            if not matched_player:
                warnings.append(f"`{row_name or '이름 없음'}`: 경기 참가자 매칭 실패")
                continue
    
            used_ids.add(str(matched_player.get("user_id")))
            matches.append((matched_player, row))
    
        missing_players = [
            get_member_display_name(guild, gid, player.get("user_id"))
            for player in players
            if str(player.get("user_id")) not in used_ids
        ]
        if missing_players:
            warnings.append("ROFL에 매칭되지 않은 참가자: " + ", ".join(missing_players[:5]))
        return matches, warnings
    
    def get_rofl_winner_side(rofl_rows):
        winners = {str(row.get("team")) for row in rofl_rows if row.get("win") is True}
        if "100" in winners and "200" not in winners:
            return "blue"
        if "200" in winners and "100" not in winners:
            return "red"
        return None
    
    def _league_rofl_partition_score(record, matches, rofl_winner=None):
        """Compare league team membership against ROFL blue/red without assuming side names."""
        record_teams = []
        for team in (record.get("teams", []) or []):
            ids = {str(uid) for uid in (team.get("players", []) or []) if str(uid)}
            if ids:
                record_teams.append(ids)
        if len(record_teams) != 2:
            return 0, 0
    
        rofl_sides = {"blue": set(), "red": set()}
        winning_uids = set()
        for player, row in matches:
            uid = str(player.get("user_id") or "")
            side = "blue" if str(row.get("team")) == "100" else "red" if str(row.get("team")) == "200" else None
            if uid and side:
                rofl_sides[side].add(uid)
            if str(player.get("result") or "").lower() == "win" and uid:
                winning_uids.add(uid)
    
        blue, red = rofl_sides["blue"], rofl_sides["red"]
        if not blue or not red:
            return 0, 0
        direct = len(record_teams[0] & blue) + len(record_teams[1] & red)
        swapped = len(record_teams[0] & red) + len(record_teams[1] & blue)
        partition_matches = max(direct, swapped)
    
        winner_bonus = 0
        if rofl_winner in ("blue", "red") and winning_uids:
            rofl_winner_uids = rofl_sides[rofl_winner]
            winner_overlap = len(winning_uids & rofl_winner_uids)
            loser_overlap = len(winning_uids - rofl_winner_uids)
            if winner_overlap >= 4 and winner_overlap > loser_overlap:
                winner_bonus = 20
            elif loser_overlap >= 4 and loser_overlap > winner_overlap:
                winner_bonus = -30
        return partition_matches, winner_bonus
    
    def get_rofl_record_match_candidates(guild, gid, records, rofl_rows, limit=200):
        """Rank saved matches against a ROFL by participant + team + role + winner.
    
        Participant overlap alone is not enough because the same ten users can play
        consecutive games with different lanes.  Team/role agreement is therefore
        treated as structural evidence and recency is only a final tie breaker.
        """
        rofl_winner = get_rofl_winner_side(rofl_rows)
        candidates = []
        checked = 0
        for rank, record in enumerate(records, 1):
            if checked >= int(limit or 200):
                break
            mode = record.get("mode", "classic")
            players = record.get("players", []) or []
            if record.get("cancelled") or mode in (EVENT_MODE_KEY, ARAM_MODE_KEY) or len(players) < 10:
                continue
            checked += 1
            matches, warnings = match_rofl_rows_to_record(guild, gid, record, rofl_rows)
            matched_count = len(matches)
            team_match_count = 0
            role_match_count = 0
            team_role_match_count = 0
            for player, row in matches:
                row_team = "blue" if str(row.get("team")) == "100" else "red" if str(row.get("team")) == "200" else None
                player_team = str(player.get("team") or "").lower()
                row_role = normalize_role_name(row.get("role"))
                player_role = normalize_role_name(player.get("role"))
                team_match = bool(row_team and player_team == row_team)
                role_match = bool(row_role and player_role and row_role == player_role)
                team_match_count += int(team_match)
                role_match_count += int(role_match)
                team_role_match_count += int(team_match and role_match)
    
            winner = str(record.get("winner", "")).lower()
            winner_bonus = 0
            if mode in (LEAGUE_SERIES_MODE_KEY, ARAM_LEAGUE_MODE_KEY):
                partition_matches, winner_bonus = _league_rofl_partition_score(record, matches, rofl_winner)
                team_match_count = max(team_match_count, partition_matches)
                if mode == LEAGUE_SERIES_MODE_KEY:
                    # 협곡 리그전은 ROFL의 라인 정보도 있으므로 팀 분할 + 라인을 함께 구조 증거로 사용한다.
                    role_match_count = sum(
                        int(bool(normalize_role_name(row.get("role"))) and normalize_role_name(row.get("role")) == normalize_role_name(player.get("role")))
                        for player, row in matches
                    )
                    team_role_match_count = min(team_match_count, role_match_count)
                else:
                    # 칼바람 리그전에는 라인이 없으므로 팀 구성 일치도가 핵심 구조 증거다.
                    role_match_count = 0
                    team_role_match_count = 0
            elif rofl_winner and winner in ("blue", "red"):
                winner_bonus = 20 if winner == rofl_winner else -30
    
            structural_score = (
                matched_count * 100
                + team_role_match_count * 80
                + role_match_count * 25
                + team_match_count * 15
                + winner_bonus
            )
            score = structural_score - min(rank, 50)
            candidates.append({
                "rank": rank,
                "record": record,
                "score": score,
                "structural_score": structural_score,
                "matched_count": matched_count,
                "team_match_count": team_match_count,
                "role_match_count": role_match_count,
                "team_role_match_count": team_role_match_count,
                "winner_match": bool(rofl_winner and winner == rofl_winner),
                "warnings": warnings,
            })
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates
    
    def format_rofl_record_candidates(candidates, limit=5):
        if not candidates:
            return "후보 없음"
        lines = []
        for idx, item in enumerate(candidates[:limit], 1):
            record = item.get("record", {})
            winner = record.get("winner", "기록 없음")
            when = record.get("time", "시간 없음")
            lines.append(
                f"{idx}순위: 최근 {item['rank']}번째 경기 · {item['matched_count']}/10명 매칭 · "
                f"팀+포지션 {item.get('team_role_match_count', 0)}/10 · 승리 {winner} · {when}"
            )
        return "\n".join(lines)
    
    def resolve_rofl_record(guild, gid, records, rofl_rows, 순번=None, 최근경기수=200):
        get_rofl_record_match_candidates = runtime["get_rofl_record_match_candidates"]
        if 순번:
            if len(records) < 순번:
                raise ValueError(f"확인 가능한 경기 기록은 {len(records)}개입니다.")
            record = records[순번 - 1]
            evidence_rows = get_rofl_record_match_candidates(guild, gid, [record], rofl_rows, 1)
            evidence = evidence_rows[0] if evidence_rows else None
            mode = record.get("mode", "classic")
            matched = int((evidence or {}).get("matched_count", 0) or 0)
            team_matched = int((evidence or {}).get("team_match_count", 0) or 0)
            role_matched = int((evidence or {}).get("role_match_count", 0) or 0)
            if mode == ARAM_LEAGUE_MODE_KEY:
                structural_ok = matched >= 8 and team_matched >= 8
            else:
                structural_ok = matched >= 8 and team_matched >= 8 and role_matched >= 8
            if not structural_ok:
                raise ValueError(
                    f"지정한 최근 {순번}번째 경기와 ROFL 참가자/팀 구성이 일치하지 않습니다. "
                    f"참가자 {matched}/10 · 팀 {team_matched}/10 · 포지션 {role_matched}/10"
                )
            return 순번, record, [f"지정한 최근 {순번}번째 경기와 ROFL을 매칭했습니다."], []
    
        candidates = get_rofl_record_match_candidates(guild, gid, records, rofl_rows, 최근경기수)
        if not candidates:
            raise ValueError("ROFL과 비교할 수 있는 최근 경기 기록을 찾지 못했습니다.")
    
        best = candidates[0]
        if best["matched_count"] < 8:
            raise ValueError(
                "자동 탐색으로 확정하기엔 매칭 인원이 부족합니다.\n"
                f"최소 기준: 8/10명 · 최고 후보: 최근 {best['rank']}번째 경기 {best['matched_count']}/10명 매칭\n\n"
                "후보 목록:\n"
                f"{format_rofl_record_candidates(candidates)}\n\n"
                "맞는 경기가 보이면 `/경기기록 [순번]`으로 확인한 뒤 "
                "`/리플레이기록 [파일] [순번]`에 순번을 직접 입력해주세요."
            )
        if len(candidates) >= 2:
            second = candidates[1]
            # If two recent games are structurally indistinguishable (same ten users,
            # same team/role layout and winner), recency must not silently choose one.
            # Ask the admin to provide an explicit recent-match rank instead.
            if (
                best.get("matched_count", 0) >= 8
                and second.get("matched_count", 0) >= 8
                and best.get("structural_score") == second.get("structural_score")
            ):
                raise ValueError(
                    "같은 참가자/팀/포지션 구성의 경기 후보가 둘 이상이라 자동으로 확정할 수 없습니다.\n\n"
                    f"후보 목록:\n{format_rofl_record_candidates(candidates)}\n\n"
                    "`/리플레이기록`의 `순번`에 `/경기기록`에서 확인한 최근 경기 번호를 지정해주세요."
                )
    
        warnings = [
            f"순번을 입력하지 않아 최근 {최근경기수}경기 안에서 자동 탐색했습니다.",
            (
                f"자동 선택: 최근 {best['rank']}번째 경기 · 참가자 {best['matched_count']}/10 · "
                f"팀+포지션 {best.get('team_role_match_count', 0)}/10 매칭"
            ),
        ]
        if len(candidates) >= 2:
            second = candidates[1]
            if best["score"] - second["score"] < 80:
                warnings.append(
                    f"2순위: 최근 {second['rank']}번째 경기 · 참가자 {second['matched_count']}/10 · "
                    f"팀+포지션 {second.get('team_role_match_count', 0)}/10 매칭"
                )
        return best["rank"], best["record"], warnings, candidates[:3]
    
    OBJECTIVE_STEAL_LABELS = {
        "DRAGON": "🐉 용",
        "BARON": "🟣 바론",
        "ELDER": "🐲 장로",
        "HERALD": "👁️ 전령",
    }
    
    
    def format_objective_steal_summary(steal_info):
        if not isinstance(steal_info, dict):
            return None
        if steal_info.get("confidence") != "confirmed":
            return None
        objective_counts = steal_info.get("objective_counts") or {}
        parts = []
        for objective in ("DRAGON", "BARON", "ELDER", "HERALD"):
            count = int(objective_counts.get(objective, 0) or 0)
            if count > 0:
                parts.append(f"{OBJECTIVE_STEAL_LABELS.get(objective, objective)} 스틸 {count}회")
        return " · ".join(parts) or None
    
    
    def get_ambiguous_objective_steal_count(steal_info):
        if not isinstance(steal_info, dict):
            return 0
        if steal_info.get("confidence") != "ambiguous":
            return 0
        return int(steal_info.get("count", 0) or 0)
    
    
    def build_rofl_detail_entries(guild, gid, record, rofl_rows):
        matches, warnings = match_rofl_rows_to_record(guild, gid, record, rofl_rows)
        duration_seconds = max(
            (int(row.get("duration_seconds", 0) or 0) for row in rofl_rows),
            default=0,
        )
        if duration_seconds <= 0:
            duration_seconds = match_stats.parse_duration_seconds(record.get("duration") or "1:00")
    
        entries = []
        for order, (player, row) in enumerate(matches, 1):
            uid = str(player.get("user_id"))
            opponent = get_opponent_player_record(record, player)
            rofl_team = "blue" if str(row.get("team")) == "100" else "red" if str(row.get("team")) == "200" else player.get("team", "unknown")
            role = normalize_role_name(player.get("role")) or normalize_role_name(row.get("role")) or player.get("role") or row.get("role") or "미지정"
            entry = match_stats.build_entry(
                match_id=record.get("id"),
                user_id=uid,
                champion=row.get("champion") or "",
                role=role,
                team=rofl_team,
                result=player.get("result", "unknown"),
                kills=int(row.get("kills", 0) or 0),
                deaths=int(row.get("deaths", 0) or 0),
                assists=int(row.get("assists", 0) or 0),
                cs=int(row.get("cs", 0) or 0),
                gold=int(row.get("gold", 0) or 0),
                damage=int(row.get("damage_to_champions", 0) or 0),
                duration_seconds=duration_seconds,
                team_kills=0,
                before_mmr=player.get("before_mmr", 0),
                opponent_mmr=opponent.get("before_mmr", 0) if opponent else 0,
                screenshot_name=row.get("summoner_name", ""),
                source="rofl",
                double_kills=int(row.get("double_kills", 0) or 0),
                triple_kills=int(row.get("triple_kills", 0) or 0),
                quadra_kills=int(row.get("quadra_kills", 0) or 0),
                penta_kills=int(row.get("penta_kills", 0) or 0),
                largest_multi_kill=int(row.get("largest_multi_kill", 0) or 0),
                rofl_stats=row.get("rofl_stats") or {},
            )
            steal_info = row.get("objective_steal")
            if isinstance(steal_info, dict):
                # match_stats.build_entry는 표준 상세스탯만 만들기 때문에
                # ROFL 전용 확정 스틸 판정은 별도 필드로 그대로 보존한다.
                entry["objective_steal"] = {
                    "confidence": str(steal_info.get("confidence") or "ambiguous"),
                    "count": int(steal_info.get("count", 0) or 0),
                    "objective": steal_info.get("objective"),
                    "objective_counts": {
                        str(key): int(value or 0)
                        for key, value in (steal_info.get("objective_counts") or {}).items()
                        if int(value or 0) > 0
                    },
                    "reason": str(steal_info.get("reason") or ""),
                }
            entry["source_order"] = order
            entries.append(entry)
    
        return entries, warnings, duration_seconds

    async def save_rofl_detail_for_match(interaction, gid, record, rofl_rows, *, reset_title_batch=False):
        """Persist all ROFL detail rows for a recorded 10-player match immediately.

        This is the same storage path used by /리플레이기록 confirmation, but without
        a second confirmation step when the ROFL already supplied the full match result.
        """
        entries, warnings, duration_seconds = build_rofl_detail_entries(
            interaction.guild, gid, record, rofl_rows
        )
        if len(entries) != 10:
            detail = "\n".join(warnings[:8]) if warnings else "참가자 매칭 실패"
            raise ValueError(
                f"ROFL 상세기록을 10명 모두 만들지 못했습니다. 현재 {len(entries)}/10명\n{detail}"
            )

        view = DetailStatConfirmView(
            gid,
            record,
            entries,
            str(interaction.user.id),
        )
        saved_count = await view.save_detail_entries(
            interaction,
            record=record,
            entries=entries,
            reset_title_batch=reset_title_batch,
        )
        await flush_title_batch(interaction, gid)
        return saved_count, warnings, duration_seconds, list(view.last_final_rating_lines or [])

    async def save_rofl_detail_for_latest_record(interaction, gid, queue_key, rofl_rows):
        history = bot.history.get(str(gid), {}).get(queue_key, {}) or {}
        match_id = history.get("match_id")
        if not match_id:
            raise RuntimeError("방금 기록한 경기의 match_id를 찾지 못했습니다.")
        record = match_stats.find_match_record(bot.user_data.setdefault(str(gid), {}), match_id)
        if not record:
            raise RuntimeError("방금 기록한 경기 기록을 찾지 못했습니다.")
        saved_count, warnings, duration_seconds, rating_lines = await save_rofl_detail_for_match(
            interaction, str(gid), record, rofl_rows, reset_title_batch=False
        )
        return {
            "record": record,
            "match_id": match_id,
            "saved_count": saved_count,
            "warnings": warnings,
            "duration_seconds": duration_seconds,
            "rating_lines": rating_lines,
        }
    
    def find_rofl_registered_user(gid, row_name):
        row_variants = rofl_name_variants(row_name)
        if not row_variants:
            return None, None, False
    
        for variant in row_variants:
            owner_uid, owner_name, is_alt = find_lol_account_owner(gid, variant)
            if owner_uid:
                return owner_uid, owner_name, is_alt
    
        for uid, data in iter_user_records(bot.user_data.get(gid, {})):
            user_info = ensure_user_format(data)
            for account_name in get_saved_lol_account_names(gid, uid):
                account_variants = rofl_name_variants(account_name)
                if row_variants & account_variants:
                    return str(uid), account_name, normalize_lol_account_key(account_name) != normalize_lol_account_key(user_info.get("lol_name"))
        return None, None, False

    def resolve_active_series_rofl_match(guild, gid, rofl_rows):
        """Find one currently playable real league-series match for this ROFL.

        A replay must resolve every participant to the exact ten user IDs in one
        active match.  Partial or ambiguous overlap is deliberately rejected so
        it cannot fall through to the generic classic retroactive path.
        """
        if len(rofl_rows or []) != 10:
            return None

        active_games = bot.active_games.get(str(gid), {}) or {}
        exact_candidates = []
        partial_candidates = []
        for queue_key in (LEAGUE_SERIES_QUEUE_KEY, ARAM_LEAGUE_QUEUE_KEY):
            game_state = active_games.get(queue_key)
            if not isinstance(game_state, dict) or game_state.get("simulation") or game_state.get("finalized"):
                continue
            if game_state.get("mode") not in (LEAGUE_SERIES_MODE_KEY, ARAM_LEAGUE_MODE_KEY):
                continue
            matches = game_state.get("matches", {}) or {}
            teams_by_no = {
                int(team.get("team_no")): team
                for team in game_state.get("teams", []) or []
                if team.get("team_no") is not None
            }
            resolved_uids = {}
            unresolved_rows = []
            duplicate_uids = set()
            for row in rofl_rows:
                uid, _matched_name, _is_alt = find_rofl_registered_user(gid, row.get("summoner_name") or "")
                if not uid:
                    unresolved_rows.append(row)
                    continue
                uid = str(uid)
                if uid in resolved_uids:
                    duplicate_uids.add(uid)
                resolved_uids[uid] = row

            for match_id in game_state.get("match_order", []) or []:
                match = matches.get(str(match_id), {}) or {}
                if not is_series_match_playable(match, matches):
                    continue
                team_nos = get_series_match_team_nos(match, matches)
                if len(team_nos) != 2 or any(no is None for no in team_nos):
                    continue
                expected_uids = {
                    str(uid)
                    for team_no in team_nos
                    for uid in (teams_by_no.get(int(team_no), {}).get("players", []) or [])
                    if uid is not None
                }
                overlap = expected_uids & set(resolved_uids)
                if len(expected_uids) != 10 or not overlap:
                    continue
                if (
                    unresolved_rows
                    or duplicate_uids
                    or len(resolved_uids) != 10
                    or set(resolved_uids) != expected_uids
                ):
                    if len(overlap) >= 8:
                        partial_candidates.append((queue_key, match_id, len(overlap)))
                    continue

                side_by_team = {}
                invalid_side = False
                for team_no in team_nos:
                    team_uids = {
                        str(uid)
                        for uid in (teams_by_no.get(int(team_no), {}).get("players", []) or [])
                    }
                    sides = {
                        "blue" if str(resolved_uids[uid].get("team")) == "100"
                        else "red" if str(resolved_uids[uid].get("team")) == "200"
                        else None
                        for uid in team_uids
                    }
                    if len(sides) != 1 or None in sides:
                        invalid_side = True
                        break
                    side_by_team[int(team_no)] = next(iter(sides))
                if invalid_side or set(side_by_team.values()) != {"blue", "red"}:
                    partial_candidates.append((queue_key, match_id, len(overlap)))
                    continue

                winner_side = get_rofl_winner_side(rofl_rows)
                if winner_side not in side_by_team.values():
                    raise ValueError(
                        f"진행 중 {get_series_mode_name(game_state)} 매치 {match_id}와 ROFL의 승리팀 정보를 연결하지 못했습니다."
                    )
                winning_rows = [row for row in rofl_rows if row.get("win") is True]
                if len(winning_rows) < 4:
                    raise ValueError("ROFL 승리팀 참가자 수가 부족해 리그전 결과를 자동 반영할 수 없습니다.")
                winner_no = next(no for no, side in side_by_team.items() if side == winner_side)
                winner_team = teams_by_no.get(int(winner_no))
                if not winner_team:
                    raise ValueError("진행 중 리그전 승리팀 정보를 찾지 못했습니다.")
                record_builder = runtime.get("build_series_match_history_record")
                if not callable(record_builder):
                    raise RuntimeError("리그전 경기 기록 생성 함수를 찾지 못했습니다.")
                loser_no = next(no for no in team_nos if int(no) != int(winner_no))
                loser_team = teams_by_no.get(int(loser_no))
                if not loser_team:
                    raise ValueError("진행 중 리그전 패배팀 정보를 찾지 못했습니다.")
                record = record_builder(gid, game_state, match, winner_team, loser_team)
                record["id"] = f"series-preview-{queue_key}-{match_id}"
                exact_candidates.append({
                    "queue_key": queue_key,
                    "match_no": int(match.get("match_no", match_id)),
                    "winner_no": int(winner_no),
                    "winner_text": format_league_team_name(winner_team),
                    "record": record,
                    "warnings": [
                        f"진행 중 {get_series_mode_name(game_state)} 매치 {match_id}에 ROFL 참가자 10/10명 일치",
                        f"ROFL 결과로 {format_league_team_name(winner_team)} 승리팀을 확인했습니다.",
                    ],
                })

        if len(exact_candidates) > 1:
            labels = ", ".join(
                f"{item['queue_key']} M{item['match_no']}" for item in exact_candidates
            )
            raise ValueError(f"진행 중 리그전 매치 후보가 둘 이상이라 자동 반영할 수 없습니다: {labels}")
        if partial_candidates:
            labels = ", ".join(
                f"{queue_key} M{match_id} ({overlap}/10명)"
                for queue_key, match_id, overlap in partial_candidates
            )
            raise ValueError(
                "ROFL 참가자가 진행 중 리그전과 일부만 일치합니다. "
                f"자동 소급 반영을 중단했습니다: {labels}"
            )
        return exact_candidates[0] if exact_candidates else None

    def build_retroactive_rofl_match(guild, gid, rofl_rows):
        if len(rofl_rows) != 10:
            raise ValueError(f"지난 경기 반영은 ROFL 참가자가 정확히 10명일 때만 가능합니다. 현재 {len(rofl_rows)}명")
    
        used_uids = set()
        warnings = ["기존 경기 기록이 없어 ROFL 참가자 10명으로 소급 경기 후보를 만들었습니다."]
        players_by_team = {"blue": [], "red": []}
        roles_map = {}
        lineup_mmr = {}
    
        for row in rofl_rows:
            row_name = row.get("summoner_name") or ""
            uid, matched_name, is_alt = find_rofl_registered_user(gid, row_name)
            if not uid:
                raise ValueError(f"`{row_name or '이름 없음'}` 계정을 등록된 서버 소환사/부계정에서 찾지 못했습니다.")
            if uid in used_uids:
                raise ValueError(f"`{row_name}` 계정이 이미 다른 ROFL 참가자와 같은 유저로 매칭되었습니다.")
    
            team = "blue" if str(row.get("team")) == "100" else "red" if str(row.get("team")) == "200" else None
            if team not in ("blue", "red"):
                raise ValueError(f"`{row_name}` 의 팀 정보를 ROFL에서 확인하지 못했습니다.")
    
            role = normalize_role_name(row.get("role"))
            if role not in ROLES:
                raise ValueError(f"`{row_name}` 의 라인 정보를 ROFL에서 확인하지 못했습니다.")
    
            user_info = ensure_user_format(bot.user_data.get(gid, {}).get(uid, make_default_user(str(matched_name or uid))))
            before_mmr = int(user_info.get("mmr", {}).get(role, 0) or 0)
            if before_mmr <= 0:
                raise ValueError(f"`{row_name}` -> {get_member_display_name(guild, gid, uid)} 님의 `{role}` MMR이 없어 지난 경기로 반영할 수 없습니다.")
    
            member = guild.get_member(int(uid)) if guild else None
            if guild and member is None:
                raise ValueError(
                    f"`{row_name}` -> 서버에 현재 가입된 멤버가 아니어서 지난 경기로 반영할 수 없습니다."
                )
            display_name = member.display_name if member else get_member_display_name(guild, gid, uid)
            used_uids.add(uid)
            roles_map[uid] = role
            lineup_mmr[uid] = before_mmr
            players_by_team[team].append({
                "user_id": uid,
                "name": display_name,
                "team": team,
                "role": role,
                "result": "unknown",
                "lineup_mmr": before_mmr,
                "before_mmr": before_mmr,
                "screenshot_name": row_name,
            })
            if is_alt:
                warnings.append(f"`{row_name}` → {get_member_display_name(guild, gid, uid)} 부계정 매칭")
    
        for team, players in players_by_team.items():
            if len(players) != 5:
                raise ValueError(f"ROFL {team}팀 인원이 {len(players)}명입니다. 팀당 5명일 때만 지난 경기로 반영할 수 있습니다.")
            team_roles = {player.get("role") for player in players}
            if team_roles != set(ROLES):
                missing = ", ".join(role for role in ROLES if role not in team_roles)
                raise ValueError(f"ROFL {team}팀 라인 구성이 완전하지 않습니다. 누락: {missing or '확인 필요'}")
    
        winner = get_rofl_winner_side(rofl_rows)
        if winner not in ("blue", "red"):
            raise ValueError("ROFL 승리팀 정보를 확인하지 못했습니다.")
    
        for player in players_by_team["blue"] + players_by_team["red"]:
            player["result"] = "win" if player.get("team") == winner else "loss"
    
        temp_id = f"retro-preview-{now_kst().strftime('%Y%m%d%H%M%S')}"
        record = {
            "id": temp_id,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            "queue": "retro",
            "mode": "classic",
            "winner": winner,
            "blue": [player["user_id"] for player in sorted(players_by_team["blue"], key=lambda p: ROLES.index(p["role"]))],
            "red": [player["user_id"] for player in sorted(players_by_team["red"], key=lambda p: ROLES.index(p["role"]))],
            "players": sorted(players_by_team["blue"], key=lambda p: ROLES.index(p["role"]))
            + sorted(players_by_team["red"], key=lambda p: ROLES.index(p["role"])),
            "cancelled": False,
            "retroactive_rofl": True,
        }
        game_state = {
            "mode": "classic",
            "roles": roles_map,
            "lineup_mmr": lineup_mmr,
            "blue": list(record["blue"]),
            "red": list(record["red"]),
            "retroactive_rofl": True,
        }
        return record, game_state, warnings
    
    def get_entry_missing_fields(entry):
        missing = []
        if not str(entry.get("champion") or "").strip():
            missing.append("챔피언")
        if all(int(entry.get(key, 0) or 0) == 0 for key in ("kills", "deaths", "assists")):
            missing.append("KDA")
        if int(entry.get("damage", 0) or 0) <= 0:
            missing.append("딜량/분당 피해량")
        return missing
    
    def sorted_record_players_for_detail(record):
        def sort_key(player):
            team_order = 0 if player.get("team") == "blue" else 1
            role_order = ROLES.index(player.get("role")) if player.get("role") in ROLES else 99
            return (team_order, role_order, str(player.get("name") or ""))
        return sorted(record.get("players", []), key=sort_key)
    
    def get_missing_detail_rows(guild_data, record):
        match_id = record.get("id")
        store = match_stats.get_store(guild_data).get(str(match_id), {})
        rows = []
        for idx, player in enumerate(sorted_record_players_for_detail(record), 1):
            uid = str(player.get("user_id"))
            entry = store.get(uid)
            if not entry:
                rows.append((idx, player, None, ["전체"]))
                continue
            missing = get_entry_missing_fields(entry)
            if missing:
                rows.append((idx, player, entry, missing))
        return rows
    
    def format_missing_detail_lines(guild, gid, record, guild_data, limit=10):
        lines = []
        for idx, player, entry, missing in get_missing_detail_rows(guild_data, record)[:limit]:
            uid = str(player.get("user_id"))
            champion = (entry or {}).get("champion") or "미입력"
            if entry:
                kda = f"{entry.get('kills', 0)}/{entry.get('deaths', 0)}/{entry.get('assists', 0)}"
                damage = f"{int(entry.get('damage', 0) or 0):,}"
            else:
                kda = "미입력"
                damage = "미입력"
            lines.append(
                f"`{idx}` {get_member_label(guild, gid, uid)} `{player.get('role', '미지정')}` · "
                f"누락 **{', '.join(missing)}**\n"
                f"└ 챔피언 {champion} · KDA {kda} · 딜량 {damage}"
            )
        return lines
    
    async def analyze_rofl_detail_file(attachment):
        if not str(attachment.filename or "").lower().endswith(".rofl"):
            raise ValueError(".rofl 파일만 업로드할 수 있습니다.")
        validate_rofl_upload_size(attachment)
        raw = await attachment.read()
        if not raw:
            raise ValueError("업로드된 ROFL 파일이 비어 있습니다.")
        validate_rofl_upload_size(attachment, raw)
        try:
            champion_map = await asyncio.wait_for(asyncio.to_thread(get_rofl_champion_map), timeout=6)
        except Exception as exc:
            logger.warning("ROFL champion map load timed out or failed: %s", exc)
            champion_map = None
        return await asyncio.to_thread(rofl.read_rofl_player_stats, raw, champion_map)
    
    def build_local_screenshot_detail_entries(record, champion_rows, scoreboard_rows, damage_rows, duration_seconds, shooter_id=None):
        row_players, warnings = get_scoreboard_row_player_map(record, shooter_id=shooter_id)
        champions_by_row = {
            row: (result.get("best") or (result.get("candidates") or [None])[0])
            for row, result in enumerate(champion_rows, 1)
        }
        numbers_by_row = {row.get("row"): row for row in scoreboard_rows}
        damage_by_row = {row.get("row"): row for row in damage_rows}
    
        entries = []
        for row in range(1, 11):
            player = row_players.get(row)
            if not player:
                continue
    
            uid = str(player.get("user_id"))
            number_row = numbers_by_row.get(row, {})
            damage_row = damage_by_row.get(row, {})
            kda = number_row.get("kda")
            damage = int(damage_row.get("damage", 0) or 0)
            champion = champions_by_row.get(row) or {}
            champion_name = str(champion.get("name") or "").strip()
    
            if not kda:
                candidates = ", ".join(number_row.get("kda_candidates", [])) or "후보 없음"
                warnings.append(f"{row}줄 {player.get('name', uid)}: KDA 확인 필요 ({candidates})")
                continue
            if damage <= 0:
                warnings.append(f"{row}줄 {player.get('name', uid)}: 딜량 OCR 확인 필요")
                continue
            if not champion_name:
                warnings.append(f"{row}줄 {player.get('name', uid)}: 챔피언 매칭 실패")
                continue
    
            cs = int(number_row.get("cs", 0) or 0)
            gold = int(number_row.get("gold", 0) or 0)
            if number_row.get("cs_checked") and cs <= 0:
                warnings.append(f"{row}줄 {player.get('name', uid)}: CS가 0으로 인식됨")
            if number_row.get("gold_checked") and gold <= 0:
                warnings.append(f"{row}줄 {player.get('name', uid)}: 골드가 0으로 인식됨")
    
            opponent = get_opponent_player_record(record, player)
            entries.append(match_stats.build_entry(
                match_id=record.get("id"),
                user_id=uid,
                champion=champion_name,
                role=player.get("role", "미지정"),
                team=player.get("team", "unknown"),
                result=player.get("result", "unknown"),
                kills=int(kda[0]),
                deaths=int(kda[1]),
                assists=int(kda[2]),
                cs=cs,
                gold=gold,
                damage=damage,
                duration_seconds=duration_seconds,
                team_kills=0,
                before_mmr=player.get("before_mmr", 0),
                opponent_mmr=opponent.get("before_mmr", 0) if opponent else 0,
                screenshot_name=f"{row}줄",
                source="local_ocr",
            ))
    
        return entries, warnings
    
    async def update_detail_progress(message, text):
        if not message:
            return
        try:
            await message.edit(content=text)
        except Exception:
            pass
    
    async def analyze_local_detail_screenshots(점수판, 딜량그래프, record, shooter_id=None, progress_message=None):
        await update_detail_progress(progress_message, "📥 이미지 다운로드 중...")
        scoreboard_bytes, damage_bytes = await asyncio.gather(
            점수판.read(),
            딜량그래프.read(),
        )
    
        await update_detail_progress(progress_message, "🔎 점수판 분석 중... (챔피언/KDA/경기시간, 시간이 조금 걸릴 수 있음)")
        champion_rows, scoreboard_rows, match_duration = await asyncio.gather(
            asyncio.to_thread(screenshot_stats.analyze_scoreboard_champions, scoreboard_bytes, 1),
            asyncio.to_thread(screenshot_stats.ocr_scoreboard_core_numbers, scoreboard_bytes),
            asyncio.to_thread(screenshot_stats.ocr_match_duration, scoreboard_bytes),
        )
    
        await update_detail_progress(progress_message, "📊 딜량 그래프 OCR 중... (시간이 조금 걸릴 수 있음)")
        damage_rows = await asyncio.to_thread(screenshot_stats.ocr_damage_numbers_fast, damage_bytes)
    
        await update_detail_progress(progress_message, "🧩 경기 기록과 스샷 줄 매칭 중...")
        duration_seconds = match_stats.parse_duration_seconds(match_duration or record.get("duration"))
        if duration_seconds <= 0:
            duration_seconds = match_stats.parse_duration_seconds("1:00")
        entries, warnings = build_local_screenshot_detail_entries(
            record,
            champion_rows,
            scoreboard_rows,
            damage_rows,
            duration_seconds,
            shooter_id=shooter_id,
        )
        await update_detail_progress(progress_message, "✅ 분석 완료. 결과 메시지를 생성하는 중...")
        return entries, warnings, duration_seconds
    
    def build_local_detail_preview_embed(guild, gid, record, entries, warnings, duration_seconds, 순번, *, test_mode=False, source_label="스샷"):
        preview_store = {}
        for entry in entries:
            match_stats.upsert_entry(preview_store, entry)
        preview_awards = match_stats.score_match_awards(preview_store, record.get("id"))
        match_label = f"최근 **{순번}번째 경기**" if isinstance(순번, int) else f"**{순번} 경기**"
    
        embed = discord.Embed(
            title=f"🧪 상세 스탯 {source_label} 분석 테스트" if test_mode else f"🧪 상세 스탯 {source_label} 분석 결과",
            description=(
                f"{match_label} (`{record.get('id')}`) · "
                f"**{len(entries)}명** · **{match_stats.format_duration(duration_seconds)}**\n"
                f"{source_label} 데이터와 경기 기록을 매칭했습니다."
            ),
            color=0x95a5a6 if test_mode else 0x2ecc71
        )
    
        is_rofl = any(str(entry.get("source")) == "rofl" for entry in entries)
    
        def row_number(entry):
            if "source_order" in entry:
                return int(entry.get("source_order", 99) or 99)
            match = re.search(r"\d+", str(entry.get("screenshot_name", "")))
            return int(match.group(0)) if match else 99
    
        team_lines = {1: [], 2: []}
        team_names = {1: "1팀", 2: "2팀"}
        if is_rofl:
            team_names = {1: "블루팀", 2: "레드팀"}
    
        def preview_sort_key(entry):
            if is_rofl:
                team_order = 0 if entry.get("team") == "blue" else 1
                role_order = ROLES.index(entry.get("role")) if entry.get("role") in ROLES else 99
                return (team_order, role_order, row_number(entry))
            return (row_number(entry),)
    
        mvp_uid = str((preview_awards.get("mvp") or {}).get("user_id") or "")
        ace_uid = str((preview_awards.get("ace") or {}).get("user_id") or "")
    
        for entry in sorted(entries[:10], key=preview_sort_key):
            row_no = row_number(entry)
            if is_rofl:
                screen_team = 1 if entry.get("team") == "blue" else 2
                row_label = str(entry.get("role") or "미지정")
            else:
                screen_team = 1 if row_no <= 5 else 2
                row_label = str(row_no)
            name = get_member_display_name(guild, gid, entry["user_id"])
            if is_rofl:
                badges = []
                uid = str(entry.get("user_id") or "")
                if uid == mvp_uid:
                    badges.append("🥇")
                if uid == ace_uid:
                    badges.append("🛡️")
                badge_text = f" {' '.join(badges)}" if badges else ""
                team_lines[screen_team].append(
                    f"`{row_label}` **{name}** · {entry['champion']}{badge_text}"
                )
            else:
                team_lines[screen_team].append(
                    f"`{row_label}` **{name}** `{entry['role']}` {entry['champion']} · "
                    f"{entry['kills']}/{entry['deaths']}/{entry['assists']} · {entry['damage']:,}"
                )
    
        embed.add_field(name=team_names[1], value="\n".join(team_lines[1]) or "기록 없음", inline=False)
        embed.add_field(name=team_names[2], value="\n".join(team_lines[2]) or "기록 없음", inline=False)
        if not is_rofl:
            embed.add_field(
                name="MVP / ACE",
                value=(
                    f"🏅 MVP {format_award_summary(guild, gid, preview_awards.get('mvp'))}\n"
                    f"🛡️ ACE {format_award_summary(guild, gid, preview_awards.get('ace'))}"
                ),
                inline=False
            )
        if is_rofl:
            confirmed_steal_lines = []
            ambiguous_steal_lines = []
            for entry in entries:
                steal_info = entry.get("objective_steal")
                summary = format_objective_steal_summary(steal_info)
                name = get_member_display_name(guild, gid, entry["user_id"])
                if summary:
                    confirmed_steal_lines.append(f"**{name}** · {summary}")
                    continue
                ambiguous_count = get_ambiguous_objective_steal_count(steal_info)
                if ambiguous_count > 0:
                    ambiguous_steal_lines.append(
                        f"**{name}** · 스틸 {ambiguous_count}회 감지 · 종류 미확정"
                    )
            if confirmed_steal_lines or ambiguous_steal_lines:
                steal_lines = confirmed_steal_lines + ambiguous_steal_lines
                embed.add_field(
                    name="🎯 ROFL 오브젝트 스틸",
                    value="\n".join(steal_lines[:10]),
                    inline=False,
                )
    
        if warnings:
            if is_rofl:
                auto_line = next((line for line in warnings if str(line).startswith("자동 선택:")), None)
                if auto_line:
                    clean_line = str(auto_line).replace("자동 선택:", "✅ 자동 매칭 완료 ·", 1)
                    embed.add_field(name="🔗 경기 연결", value=clean_line, inline=False)
                else:
                    embed.add_field(name="🔗 경기 연결", value="✅ 경기 기록과 ROFL 연결 완료", inline=False)
            else:
                warning_text = "\n".join(f"• {line}" for line in warnings[:4])
                if len(warnings) > 4:
                    warning_text += f"\n• 외 {len(warnings) - 4}건"
                embed.add_field(name="확인 필요", value=warning_text, inline=False)
        elif is_rofl:
            embed.add_field(name="🔗 경기 연결", value="✅ 경기 기록과 ROFL 연결 완료", inline=False)
    
        if test_mode:
            embed.set_footer(text="테스트 전용입니다. 이 결과는 저장되지 않습니다.")
        return embed
    
    async def detail_stat_screenshot_test(
        interaction: discord.Interaction,
        점수판: discord.Attachment,
        딜량그래프: discord.Attachment,
        순번: app_commands.Range[int, 1, 50] = 1,
        촬영자: discord.Member = None,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 상세 스탯을 테스트할 수 있습니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
        if len(records) < 순번:
            return await interaction.response.send_message(
                f"⚠️ 확인 가능한 경기 기록은 {len(records)}개입니다.",
                ephemeral=True
            )
    
        await interaction.response.defer(thinking=True)
        record = records[순번 - 1]
        progress_message = await interaction.followup.send("🧪 데이터기록테스트 준비 중...", ephemeral=True, wait=True)
        try:
            entries, warnings, duration_seconds = await analyze_local_detail_screenshots(
                점수판,
                딜량그래프,
                record,
                shooter_id=str(촬영자.id) if 촬영자 else None,
                progress_message=progress_message,
            )
        except Exception as exc:
            await update_detail_progress(progress_message, "⚠️ 데이터기록테스트 실패")
            return await interaction.followup.send(f"⚠️ 스샷 분석 테스트 실패: `{str(exc)[:900]}`", ephemeral=True)
    
        if not entries:
            warning_text = "\n".join(warnings[:10]) if warnings else "OCR 결과가 비어 있습니다."
            await update_detail_progress(progress_message, "⚠️ 데이터기록테스트 결과 없음")
            return await interaction.followup.send(
                f"⚠️ 테스트 가능한 상세 스탯을 만들지 못했습니다.\n{warning_text}",
                ephemeral=True
            )
    
        embed = build_local_detail_preview_embed(
            interaction.guild,
            gid,
            record,
            entries,
            warnings,
            duration_seconds,
            순번,
            test_mode=True,
        )
        await update_detail_progress(progress_message, "✅ 데이터기록테스트 완료")
        await interaction.followup.send(embed=embed)
    
    async def detail_stat_screenshot_analyze(
        interaction: discord.Interaction,
        점수판: discord.Attachment,
        딜량그래프: discord.Attachment,
        순번: app_commands.Range[int, 1, 50] = 1,
        촬영자: discord.Member = None,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 상세 스탯을 분석할 수 있습니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
        if len(records) < 순번:
            return await interaction.response.send_message(
                f"⚠️ 확인 가능한 경기 기록은 {len(records)}개입니다.",
                ephemeral=True
            )
    
        await interaction.response.defer(thinking=True)
        record = records[순번 - 1]
        progress_message = await interaction.followup.send("🧪 데이터기록 준비 중...", ephemeral=True, wait=True)
        try:
            entries, warnings, duration_seconds = await analyze_local_detail_screenshots(
                점수판,
                딜량그래프,
                record,
                shooter_id=str(촬영자.id) if 촬영자 else None,
                progress_message=progress_message,
            )
        except Exception as exc:
            await update_detail_progress(progress_message, "⚠️ 데이터기록 실패")
            return await interaction.followup.send(f"⚠️ 스샷 OCR 분석 실패: `{str(exc)[:900]}`", ephemeral=True)
        if not entries:
            warning_text = "\n".join(warnings[:10]) if warnings else "OCR 결과가 비어 있습니다."
            await update_detail_progress(progress_message, "⚠️ 데이터기록 결과 없음")
            return await interaction.followup.send(
                f"⚠️ 저장 가능한 상세 스탯을 만들지 못했습니다.\n{warning_text}",
                ephemeral=True
            )
    
        embed = build_local_detail_preview_embed(interaction.guild, gid, record, entries, warnings, duration_seconds, 순번)
        view = DetailStatConfirmView(gid, record, entries, str(interaction.user.id))
        await update_detail_progress(progress_message, "✅ 데이터기록 분석 완료")
        await interaction.followup.send(embed=embed, view=view)
    
    async def detail_stat_rofl_test(
        interaction: discord.Interaction,
        파일: discord.Attachment,
        순번: app_commands.Range[int, 1, 500] = None,
        최근경기수: app_commands.Range[int, 10, 500] = 200,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 ROFL 상세 스탯을 테스트할 수 있습니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
    
        await interaction.response.defer(thinking=True)
        try:
            rofl_rows = await analyze_rofl_detail_file(파일)
            retroactive_state = None
            tournament_state = None
            if not 순번:
                tournament_state = resolve_active_series_rofl_match(interaction.guild, gid, rofl_rows)
            if tournament_state:
                record = tournament_state["record"]
                auto_warnings = list(tournament_state["warnings"])
                순번 = f"M{tournament_state['match_no']}"
            else:
                try:
                    순번, record, auto_warnings, _candidates = resolve_rofl_record(
                        interaction.guild,
                        gid,
                        records,
                        rofl_rows,
                        순번=순번,
                        최근경기수=최근경기수,
                    )
                except Exception as resolve_exc:
                    if 순번:
                        raise
                    candidates = get_rofl_record_match_candidates(interaction.guild, gid, records, rofl_rows, 최근경기수)
                    if candidates and int(candidates[0].get("matched_count", 0) or 0) >= 8:
                        raise resolve_exc
                    record, game_state, auto_warnings = build_retroactive_rofl_match(interaction.guild, gid, rofl_rows)
                    retroactive_state = {"game_state": game_state, "winner": record.get("winner")}
                    auto_warnings.insert(0, f"기존 경기 자동 매칭 실패: {str(resolve_exc)[:160]}")
                    순번 = "소급"
            entries, warnings, duration_seconds = build_rofl_detail_entries(interaction.guild, gid, record, rofl_rows)
            warnings = auto_warnings + warnings
        except Exception as exc:
            return await interaction.followup.send(f"⚠️ ROFL 분석 테스트 실패: `{str(exc)[:900]}`", ephemeral=True)
    
        if not entries:
            warning_text = "\n".join(warnings[:10]) if warnings else "ROFL 결과가 비어 있습니다."
            return await interaction.followup.send(
                f"⚠️ 테스트 가능한 상세 스탯을 만들지 못했습니다.\n{warning_text}",
                ephemeral=True
            )
    
        embed = build_local_detail_preview_embed(
            interaction.guild,
            gid,
            record,
            entries,
            warnings,
            duration_seconds,
            순번,
            test_mode=True,
            source_label="ROFL",
        )
        if retroactive_state:
            embed.add_field(
                name="지난 경기 반영 가능",
                value="기존 경기 기록이 없는 ROFL입니다. 저장 화면의 `지난 경기 반영` 버튼으로 점수와 전적까지 반영할 수 있습니다.",
                inline=False,
            )
        await interaction.followup.send(embed=embed)
    
    
    def is_already_saved_rofl_detail(gid, record, entries):
        """Return True only when this ROFL's parsed detail already exists for the matched game."""
        if not record or not entries:
            return False
    
        match_id = str(record.get("id") or "").strip()
        if not match_id or match_id.startswith("retro-preview-"):
            return False
    
        guild_data = bot.user_data.get(str(gid), {})
        if not isinstance(guild_data, dict):
            return False
    
        detail_store = guild_data.get(getattr(match_stats, "DETAIL_STATS_KEY", "_match_detail_stats"), {}) or {}
        match_store = detail_store.get(match_id, {})
        if not isinstance(match_store, dict) or not match_store:
            return False
    
        # A partial old record should still be allowed through so the ROFL can fill
        # missing users. Only suppress save when every parsed participant is already
        # stored with the same game result/stats.
        if len(match_store) < len(entries):
            return False
    
        def norm_text(value):
            return str(value or "").strip().casefold()
    
        exact_int_fields = (
            "kills",
            "deaths",
            "assists",
            "cs",
            "gold",
            "damage",
        )
    
        for incoming in entries:
            uid = str(incoming.get("user_id") or "")
            existing = match_store.get(uid)
            if not isinstance(existing, dict):
                return False
    
            for key in ("champion", "role", "team", "result"):
                if norm_text(existing.get(key)) != norm_text(incoming.get(key)):
                    return False
    
            for key in exact_int_fields:
                if int(existing.get(key, 0) or 0) != int(incoming.get(key, 0) or 0):
                    return False
    
            # Duration can differ by a second or two depending on parser/source
            # normalization, so keep a tiny tolerance.
            old_duration = int(existing.get("duration_seconds", 0) or 0)
            new_duration = int(incoming.get("duration_seconds", 0) or 0)
            if old_duration > 0 and new_duration > 0 and abs(old_duration - new_duration) > 2:
                return False
    
        return True
    
    
    def mark_rofl_preview_as_already_saved(embed):
        """Replace the normal match-link field with a duplicate-record notice."""
        replaced = False
        for index, field in enumerate(list(embed.fields)):
            if str(field.name) == "🔗 경기 연결":
                embed.set_field_at(
                    index,
                    name="✅ 이미 기록된 리플레이",
                    value="이 ROFL은 해당 경기의 상세 기록으로 이미 저장되어 있습니다.",
                    inline=False,
                )
                replaced = True
                break
    
        if not replaced:
            embed.add_field(
                name="✅ 이미 기록된 리플레이",
                value="이 ROFL은 해당 경기의 상세 기록으로 이미 저장되어 있습니다.",
                inline=False,
            )
        return embed
    
    
    async def detail_stat_rofl_analyze(
        interaction: discord.Interaction,
        파일: discord.Attachment,
        순번: app_commands.Range[int, 1, 500] = None,
        최근경기수: app_commands.Range[int, 10, 500] = 200,
    ):
        _sync_runtime()
        analyze_rofl_detail_file = runtime["analyze_rofl_detail_file"]
        resolve_rofl_record = runtime["resolve_rofl_record"]
        get_rofl_record_match_candidates = runtime["get_rofl_record_match_candidates"]
        build_retroactive_rofl_match = runtime["build_retroactive_rofl_match"]
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 ROFL 상세 스탯을 분석할 수 있습니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
    
        await interaction.response.defer(thinking=True)
        try:
            rofl_rows = await analyze_rofl_detail_file(파일)
            retroactive_state = None
            tournament_state = None
            if not 순번:
                tournament_state = resolve_active_series_rofl_match(interaction.guild, gid, rofl_rows)
            if tournament_state:
                record = tournament_state["record"]
                auto_warnings = list(tournament_state["warnings"])
                순번 = f"M{tournament_state['match_no']}"
            else:
                try:
                    순번, record, auto_warnings, _candidates = resolve_rofl_record(
                        interaction.guild,
                        gid,
                        records,
                        rofl_rows,
                        순번=순번,
                        최근경기수=최근경기수,
                    )
                except Exception as resolve_exc:
                    if 순번:
                        raise
                    candidates = get_rofl_record_match_candidates(interaction.guild, gid, records, rofl_rows, 최근경기수)
                    if candidates and int(candidates[0].get("matched_count", 0) or 0) >= 8:
                        raise resolve_exc
                    record, game_state, auto_warnings = build_retroactive_rofl_match(interaction.guild, gid, rofl_rows)
                    retroactive_state = {"game_state": game_state, "winner": record.get("winner")}
                    auto_warnings.insert(0, f"기존 경기 자동 매칭 실패: {str(resolve_exc)[:160]}")
                    순번 = "소급"
            entries, warnings, duration_seconds = build_rofl_detail_entries(interaction.guild, gid, record, rofl_rows)
            warnings = auto_warnings + warnings
        except Exception as exc:
            return await interaction.followup.send(f"⚠️ ROFL 분석 실패: `{str(exc)[:900]}`", ephemeral=True)
    
        if not entries:
            warning_text = "\n".join(warnings[:10]) if warnings else "ROFL 결과가 비어 있습니다."
            return await interaction.followup.send(
                f"⚠️ 저장 가능한 상세 스탯을 만들지 못했습니다.\n{warning_text}",
                ephemeral=True
            )
    
        embed = build_local_detail_preview_embed(
            interaction.guild,
            gid,
            record,
            entries,
            warnings,
            duration_seconds,
            순번,
            source_label="ROFL",
        )
    
        # 이미 같은 경기/참가자/최종 스탯이 저장되어 있으면 중복 저장 UI를 띄우지 않는다.
        # 일부 유저만 저장된 불완전 기록은 False가 되어 기존처럼 확정 저장으로 보완 가능하다.
        if retroactive_state is None and tournament_state is None and is_already_saved_rofl_detail(gid, record, entries):
            mark_rofl_preview_as_already_saved(embed)
            return await interaction.followup.send(embed=embed)
    
        view = DetailStatConfirmView(
            gid,
            record,
            entries,
            str(interaction.user.id),
            retroactive_state=retroactive_state,
            tournament_state=tournament_state,
        )
        await interaction.followup.send(embed=embed, view=view)
    
    def build_rofl_score_check_entries(rofl_rows):
        """Build non-persistent final-score entries when no bot match record exists."""
        entries = []
        for row in rofl_rows:
            name = str(row.get("summoner_name") or "").strip()
            role = normalize_role_name(row.get("role")) or str(row.get("role") or "미지정")
            team = "blue" if str(row.get("team")) == "100" else "red" if str(row.get("team")) == "200" else "unknown"
            result = "win" if row.get("win") is True else "loss" if row.get("win") is False else "unknown"
            entries.append(match_stats.build_entry(
                match_id="rofl-score-check",
                user_id=name,
                champion=row.get("champion") or "",
                role=role,
                team=team,
                result=result,
                kills=int(row.get("kills", 0) or 0),
                deaths=int(row.get("deaths", 0) or 0),
                assists=int(row.get("assists", 0) or 0),
                cs=int(row.get("cs", 0) or 0),
                gold=int(row.get("gold", 0) or 0),
                damage=int(row.get("damage_to_champions", 0) or 0),
                duration_seconds=int(row.get("duration_seconds", 0) or 0),
                screenshot_name=name,
                source="rofl_score_check",
                rofl_stats=row.get("rofl_stats") or {},
            ))
        for entry in entries:
            match_stats.enrich_entry(entry, {item["user_id"]: item for item in entries})
        return entries
    
    def find_rofl_score_check_pair(entries, riot_id):
        input_name = normalize_rofl_match_name(riot_id)
        if not input_name:
            return None, None
    
        def entry_name(entry):
            return normalize_rofl_match_name(entry.get("screenshot_name") or entry.get("user_id"))
    
        # A full Riot ID must match the full tag. Falling back to the name part
        # here can select a different account when a game contains duplicate names.
        if "#" in input_name:
            target = next((entry for entry in entries if entry_name(entry) == input_name), None)
        else:
            candidates = [
                entry for entry in entries
                if entry_name(entry) == input_name or entry_name(entry).split("#", 1)[0] == input_name
            ]
            target = candidates[0] if len(candidates) == 1 else None
        if not target:
            return None, None
    
        opponent = next(
            (
                entry for entry in entries
                if entry.get("team") != target.get("team") and entry.get("role") == target.get("role")
            ),
            None,
        )
        return target, opponent
    
    
    def make_rofl_ai_timeline_file(frames, target_user_id, opponent_user_id=None):
        """Render supplied real timeline frames; never infer missing ROFL frames."""
        if not plt or not frames:
            return None
        timeline = match_stats.score_timeline_frames(frames)
        if not timeline.get("available"):
            return None
    
        target_id = str(target_user_id)
        opponent_id = str(opponent_user_id) if opponent_user_id is not None else None
        target_points = []
        opponent_points = []
        for frame in timeline.get("frames", []):
            scored = {str(row.get("user_id")): row for row in frame.get("scores", [])}
            target_score = scored.get(target_id)
            if not target_score:
                continue
            minute = float(frame.get("timestamp", 0) or 0) / 60.0
            target_points.append((minute, float(target_score.get("display_score", target_score.get("expectation_score", 0)))))
            if opponent_id and opponent_id in scored:
                opponent_score = scored[opponent_id]
                opponent_points.append((minute, float(opponent_score.get("display_score", opponent_score.get("expectation_score", 0)))))
    
        if not target_points:
            return None
    
        fig, ax = plt.subplots(figsize=(8.5, 4.6), dpi=140)
        target_x, target_y = zip(*target_points)
        ax.plot(target_x, target_y, color="#f1c40f", linewidth=2.4, marker="o", label="Player")
        if opponent_points:
            opponent_x, opponent_y = zip(*opponent_points)
            ax.plot(
                opponent_x,
                opponent_y,
                color="#95a5a6",
                linewidth=1.4,
                alpha=0.55,
                linestyle="--",
                marker="o",
                markersize=3.5,
                label="Lane Opponent",
            )
        ax.set_title("AI Score Trend")
        ax.set_xlabel("Game Time (min)")
        ax.set_ylabel("AI Score")
        ax.grid(True, linestyle="--", alpha=0.3)
        ax.legend(loc="best")
        fig.tight_layout()
        image = io.BytesIO()
        fig.savefig(image, format="png", bbox_inches="tight")
        plt.close(fig)
        image.seek(0)
        return discord.File(image, filename="rofl_ai_score_timeline.png")
    
    
    def summarize_rofl_ai_timeline(frames, target_user_id, opponent_user_id=None):
        """Describe only meaningful gaps from supplied real 5-minute frames."""
        if opponent_user_id is None:
            return None
        timeline = match_stats.score_timeline_frames(frames)
        if not timeline.get("available"):
            return None
    
        target_id = str(target_user_id)
        opponent_id = str(opponent_user_id)
        lines = []
        previous_side = 0
        transition = None
        for frame in timeline.get("frames", []):
            scored = {str(row.get("user_id")): row for row in frame.get("scores", [])}
            target = scored.get(target_id)
            opponent = scored.get(opponent_id)
            if not target or not opponent:
                continue
            target_value = float(target.get("display_score", target.get("expectation_score", 0)) or 0)
            opponent_value = float(opponent.get("display_score", opponent.get("expectation_score", 0)) or 0)
            gap = target_value - opponent_value
            if abs(gap) < 3:
                continue
    
            minute = int(float(frame.get("timestamp", 0) or 0) // 60)
            side = 1 if gap > 0 else -1
            if previous_side and previous_side != side and transition is None:
                transition = f"{minute}분부터 {'우위' if side > 0 else '열세'}로 전환되었습니다."
            previous_side = side
    
            metrics = []
            for label, key, scale in (
                ("골드 획득", "gpm", 500.0),
                ("교전 피해", "dpm", 1000.0),
                ("킬 관여", "kp", 100.0),
                ("KDA", "kda", 5.0),
                ("오브젝트 관여", "objective_participation", 3.0),
            ):
                difference = float(target.get(key, 0) or 0) - float(opponent.get(key, 0) or 0)
                signed_strength = (difference / scale) * side
                if signed_strength >= 0.08:
                    metrics.append((signed_strength, label))
            metrics.sort(reverse=True)
            reason = "·".join(label for _strength, label in metrics[:2]) or "종합 지표"
            degree = "뚜렷한" if abs(gap) >= 7 else "다소"
            lines.append(f"**{minute}분** · {reason}에서 {degree} {'우위' if side > 0 else '열세'}")
    
        if not lines:
            return None
        if transition:
            lines.append(transition)
        return "\n".join(lines)
    
    @bot.tree.command(name="ai스코어추이", description="[봇 오너] ROFL의 AI 점수 변곡점과 팀 흐름을 분석합니다.")
    @app_commands.describe(닉네임태그="닉네임 또는 닉네임#태그. 닉네임만 입력해도 파일에서 유일하면 자동 매칭")
    async def rofl_ai_score_timeline_check(
        interaction: discord.Interaction,
        파일: discord.Attachment,
        닉네임태그: str,
    ):
        # Acknowledge immediately. This minimizes Discord 10062/Unknown interaction
        # races on a worker that has just restarted or is briefly busy.
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
        except discord.NotFound:
            logger.warning("AI score flow command interaction expired before defer.")
            return
    
        if not is_bot_owner(interaction):
            return await interaction.followup.send("🚫 봇 오너만 사용할 수 있습니다.", ephemeral=True)
        if not str(파일.filename or "").lower().endswith(".rofl"):
            return await interaction.followup.send("⚠️ `.rofl` 리플레이 파일만 업로드해주세요.", ephemeral=True)
        try:
            validate_rofl_upload_size(파일)
            raw = await 파일.read()
            if not raw:
                raise ValueError("업로드된 ROFL 파일이 비어 있습니다.")
            validate_rofl_upload_size(파일, raw)
    
            try:
                champion_map = await asyncio.wait_for(asyncio.to_thread(get_rofl_champion_map), timeout=6)
            except Exception as exc:
                logger.warning("ROFL champion map load timed out or failed: %s", exc)
                champion_map = None
    
            # statsJson extraction is cheap. The full binary timeline decoder remains in
            # one worker thread so Render does not decompress the same replay twice in parallel.
            rofl_rows = await asyncio.to_thread(rofl.read_rofl_player_stats_from_bytes, raw, champion_map)
            resolved_riot_id, duplicate_name_matches = resolve_rofl_input_riot_id(rofl_rows, 닉네임태그)
            if not resolved_riot_id:
                if duplicate_name_matches:
                    raise ValueError(
                        "같은 닉네임의 참가자가 둘 이상입니다. 태그까지 입력해주세요: "
                        + ", ".join(duplicate_name_matches)
                    )
                names = ", ".join(str(row.get("summoner_name") or "?") for row in rofl_rows[:10])
                raise ValueError(f"입력한 닉네임을 ROFL 참가자에서 찾지 못했습니다. 참가자: {names}")
            try:
                checkpoint_analysis = await asyncio.wait_for(
                    asyncio.to_thread(run_rofl_analysis_once, rofl.read_rofl_checkpoint_analysis_from_bytes, raw),
                    timeout=75,
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    "ROFL 전체 흐름 분석이 75초를 초과해 중단되었습니다. 잠시 후 다시 시도해주세요."
                ) from exc
    
            entries = None
            matched_record = None
            gid = str(interaction.guild_id)
            records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
            candidates = get_rofl_record_match_candidates(interaction.guild, gid, records, rofl_rows, limit=500)
            if candidates and candidates[0].get("matched_count") == 10 and candidates[0].get("winner_match"):
                matched_record = candidates[0].get("record")
                entries, _warnings, _duration = build_rofl_detail_entries(
                    interaction.guild, gid, matched_record, rofl_rows,
                )
            if not entries:
                entries = build_rofl_score_check_entries(rofl_rows)
    
            target, opponent = find_rofl_score_check_pair(entries, resolved_riot_id)
            if not target:
                names = ", ".join(str(row.get("summoner_name") or "?") for row in rofl_rows[:10])
                return await interaction.followup.send(
                    f"⚠️ `{닉네임태그}`를 ROFL 참가자에서 찾지 못했습니다.\n참가자: {names}",
                    ephemeral=True,
                )
    
            normalized_target = normalize_rofl_match_name(
                target.get("screenshot_name") or target.get("user_id") or resolved_riot_id
            )
            checkpoint_participants = checkpoint_analysis.get("participants", [])
            canonical_target = normalize_rofl_match_name(resolved_riot_id)
            participant = next(
                (row for row in checkpoint_participants if normalize_rofl_match_name(row.get("riot_id")) == canonical_target),
                None,
            )
            if participant is None:
                participant_candidates = [
                    row for row in checkpoint_participants
                    if normalize_rofl_match_name(row.get("riot_id")).split("#", 1)[0] == canonical_target.split("#", 1)[0]
                ]
                participant = participant_candidates[0] if len(participant_candidates) == 1 else None
            if not participant:
                raise ValueError("ROFL 시간대 참가자 매칭에 실패했습니다.")
            participant_id = int(participant["participant_id"])
    
            final_scores = {row["user_id"]: row for row in match_stats.score_entries(entries)}
            target_final = final_scores.get(target["user_id"], {})
        except Exception as exc:
            return await interaction.followup.send(f"⚠️ ROFL AI 스코어 확인 실패: `{str(exc)[:900]}`", ephemeral=True)
    
        def rounded_score(score):
            value = float(score.get("display_score", score.get("expectation_score", 0)) or 0)
            return int(value + 0.5) if value >= 0 else int(value - 0.5)
    
        all_checkpoint_rows = []
        for frame in checkpoint_analysis.get("checkpoints", []):
            row = next(
                (item for item in frame.get("players", []) if int(item.get("participant_id", 0)) == participant_id),
                None,
            )
            if row and row.get("checkpoint_score") is not None:
                all_checkpoint_rows.append((int(frame.get("minute", 0)), row, frame))
        all_checkpoint_rows.sort(key=lambda item: item[0])
    
        if not all_checkpoint_rows:
            return await interaction.followup.send("⚠️ 시간대 AI 데이터를 생성하지 못했습니다.", ephemeral=True)
    
        target_team = str(participant.get("team") or "")
        opponent_team = "red" if target_team == "blue" else "blue"
    
        # Player swing detection.
        player_changes = []
        for previous, current in zip(all_checkpoint_rows, all_checkpoint_rows[1:]):
            prev_minute, prev_row, _prev_frame = previous
            minute, row, _frame = current
            delta = float(row["checkpoint_score"]) - float(prev_row["checkpoint_score"])
            player_changes.append({
                "from_minute": prev_minute,
                "to_minute": minute,
                "delta": delta,
                "from_score": float(prev_row["checkpoint_score"]),
                "to_score": float(row["checkpoint_score"]),
                "gold_delta": int(row.get("total_gold", 0)) - int(prev_row.get("total_gold", 0)),
                "death_delta": int(row.get("deaths", 0)) - int(prev_row.get("deaths", 0)),
                "kill_delta": int(row.get("kills", 0)) - int(prev_row.get("kills", 0)),
                "assist_delta": int(row.get("assists", 0)) - int(prev_row.get("assists", 0)),
            })
        biggest_drop = min(player_changes, key=lambda item: item["delta"]) if player_changes else None
        biggest_rise = max(player_changes, key=lambda item: item["delta"]) if player_changes else None
    
        # Team-flow series and the sharpest minute-to-minute gold/AI swing.
        team_flow = []
        for minute, _row, frame in all_checkpoint_rows:
            teams = frame.get("teams") or {}
            own = teams.get(target_team) or {}
            enemy = teams.get(opponent_team) or {}
            own_score = own.get("avg_checkpoint_score")
            enemy_score = enemy.get("avg_checkpoint_score")
            team_flow.append({
                "minute": minute,
                "gold_gap": int(own.get("gold", 0)) - int(enemy.get("gold", 0)),
                "score_gap": (
                    float(own_score) - float(enemy_score)
                    if own_score is not None and enemy_score is not None else 0.0
                ),
            })
    
        team_changes = []
        for prev, cur in zip(team_flow, team_flow[1:]):
            team_changes.append({
                "from_minute": prev["minute"],
                "to_minute": cur["minute"],
                "gold_gap_before": prev["gold_gap"],
                "gold_gap_after": cur["gold_gap"],
                "gold_swing": cur["gold_gap"] - prev["gold_gap"],
                "score_gap_before": prev["score_gap"],
                "score_gap_after": cur["score_gap"],
                "score_swing": cur["score_gap"] - prev["score_gap"],
            })
        biggest_team_loss = min(team_changes, key=lambda item: item["gold_swing"]) if team_changes else None
        biggest_team_gain = max(team_changes, key=lambda item: item["gold_swing"]) if team_changes else None
    
        # Surface multiple meaningful team momentum changes instead of only one max/min.
        # Rank by combined gold-gap swing and AI-gap swing, then keep distinct intervals.
        significant_team_changes = []
        for item in team_changes:
            gold_strength = abs(float(item["gold_swing"])) / 700.0
            score_strength = abs(float(item["score_swing"])) / 2.5
            strength = gold_strength + score_strength
            if abs(int(item["gold_swing"])) >= 700 or abs(float(item["score_swing"])) >= 2.5:
                significant_team_changes.append({**item, "strength": strength})
        significant_team_changes.sort(key=lambda item: item["strength"], reverse=True)
        significant_team_changes = significant_team_changes[:5]
        significant_team_changes.sort(key=lambda item: item["from_minute"])
    
        patch_label = ".".join(str(checkpoint_analysis.get("version") or "").split(".")[:2]) or "16.16"
        embed = discord.Embed(
            title=f"📈 경기 흐름 - {patch_label}",
            description=(
                f"🎮 **{participant.get('riot_id') or 닉네임태그}**\n"
                f"🏹 `{participant.get('role', '미지정')}` · **{participant.get('champion', '')}**"
            ),
            color=0xf1c40f,
        )
    
        # Put interpretation first, raw checkpoint numbers second.
        turning_lines = []
        if biggest_drop and biggest_drop["delta"] < -0.05:
            reasons = []
            if biggest_drop["death_delta"] > 0:
                reasons.append(f"데스 +{biggest_drop['death_delta']}")
            if biggest_drop["kill_delta"] > 0 or biggest_drop["assist_delta"] > 0:
                reasons.append(f"킬관여 +{biggest_drop['kill_delta'] + biggest_drop['assist_delta']}")
            if biggest_drop["gold_delta"]:
                reasons.append(f"개인 골드 +{biggest_drop['gold_delta']:,}")
            reason_text = " · ".join(reasons[:3])
            turning_lines.append(
                f"🔻 **{biggest_drop['from_minute']} → {biggest_drop['to_minute']}분 · 최대 하락**\n"
                f"└ `{biggest_drop['from_score']:.1f} → {biggest_drop['to_score']:.1f}` "
                f"(**{biggest_drop['delta']:.1f}점**)\n"
                + (f"└ {reason_text}" if reason_text else "")
            )
        if biggest_rise and biggest_rise["delta"] > 0.05:
            reasons = []
            if biggest_rise["kill_delta"] > 0 or biggest_rise["assist_delta"] > 0:
                reasons.append(f"킬관여 +{biggest_rise['kill_delta'] + biggest_rise['assist_delta']}")
            if biggest_rise["death_delta"] == 0:
                reasons.append("추가 데스 없음")
            if biggest_rise["gold_delta"]:
                reasons.append(f"개인 골드 +{biggest_rise['gold_delta']:,}")
            reason_text = " · ".join(reasons[:3])
            turning_lines.append(
                f"🔺 **{biggest_rise['from_minute']} → {biggest_rise['to_minute']}분 · 최대 상승**\n"
                f"└ `{biggest_rise['from_score']:.1f} → {biggest_rise['to_score']:.1f}` "
                f"(**+{biggest_rise['delta']:.1f}점**)\n"
                + (f"└ {reason_text}" if reason_text else "")
            )
        embed.add_field(
            name="🎯 개인 흐름 핵심",
            value="\n".join(line for line in turning_lines if line.strip()) or "뚜렷한 급변 구간 없음",
            inline=False,
        )
    
        team_lines = []
        if significant_team_changes:
            for item in significant_team_changes:
                direction = "🔵" if item["gold_swing"] > 0 else "🔴"
                label = "우리팀 우세 확대" if item["gold_swing"] > 0 else "상대팀 우세 확대"
                team_lines.append(
                    f"{direction} **{item['from_minute']} → {item['to_minute']}분 · {label}**\n"
                    f"└ 💰 {gold_gap_delta_text(item['gold_gap_before'], item['gold_gap_after'])} "
                    f"(**{item['gold_swing']:+,}G**)\n"
                    f"└ 📊 팀 AI 격차 `{item['score_gap_before']:+.1f} → {item['score_gap_after']:+.1f}` "
                    f"(**{item['score_swing']:+.1f}**)"
                )
        else:
            team_lines.append("큰 폭으로 움직인 팀 흐름이 없습니다.")
    
        embed.add_field(
            name="👥 팀 흐름 핵심",
            value="\n\n".join(team_lines),
            inline=False,
        )
    
        # Lane-opponent momentum. Show where the opponent gained most relative to the player,
        # not fixed 5/10/15 snapshots.
        opponent_id = next(
            (row.get("opponent_id") for _minute, row, _frame in all_checkpoint_rows if row.get("opponent_id")),
            None,
        )
        opponent_identity = None
        lane_moments = []
        if opponent_id:
            opponent_identity = next(
                (
                    row for row in checkpoint_analysis.get("participants", [])
                    if int(row.get("participant_id", 0)) == int(opponent_id)
                ),
                None,
            )
    
            lane_series = []
            for minute, row, frame in all_checkpoint_rows:
                opp_row = next(
                    (
                        candidate for candidate in frame.get("players", [])
                        if int(candidate.get("participant_id", 0)) == int(opponent_id)
                    ),
                    None,
                )
                if not opp_row:
                    continue
                lane_series.append({
                    "minute": minute,
                    "player_score": float(row.get("checkpoint_score") or 0),
                    "opp_score": float(opp_row.get("checkpoint_score") or 0),
                    "player_gold": int(row.get("total_gold", 0)),
                    "opp_gold": int(opp_row.get("total_gold", 0)),
                    "player_xp": int(row.get("xp", 0)),
                    "opp_xp": int(opp_row.get("xp", 0)),
                    "player_cs": int(row.get("lane_cs", 0)),
                    "opp_cs": int(opp_row.get("lane_cs", 0)),
                })
    
            lane_changes = []
            for prev, cur in zip(lane_series, lane_series[1:]):
                prev_score_gap = prev["player_score"] - prev["opp_score"]
                cur_score_gap = cur["player_score"] - cur["opp_score"]
                prev_gold_gap = prev["player_gold"] - prev["opp_gold"]
                cur_gold_gap = cur["player_gold"] - cur["opp_gold"]
    
                # Negative relative swing means opponent gained on the player.
                score_relative_swing = cur_score_gap - prev_score_gap
                gold_relative_swing = cur_gold_gap - prev_gold_gap
                opponent_strength = (
                    max(0.0, -score_relative_swing) / 2.0
                    + max(0.0, -gold_relative_swing) / 350.0
                )
                if score_relative_swing <= -1.8 or gold_relative_swing <= -450:
                    lane_changes.append({
                        "from_minute": prev["minute"],
                        "to_minute": cur["minute"],
                        "score_gap_before": prev_score_gap,
                        "score_gap_after": cur_score_gap,
                        "score_swing": score_relative_swing,
                        "gold_gap_before": prev_gold_gap,
                        "gold_gap_after": cur_gold_gap,
                        "gold_swing": gold_relative_swing,
                        "xp_gap_after": cur["player_xp"] - cur["opp_xp"],
                        "cs_gap_after": cur["player_cs"] - cur["opp_cs"],
                        "strength": opponent_strength,
                    })
    
            lane_changes.sort(key=lambda item: item["strength"], reverse=True)
            lane_moments = lane_changes[:4]
            lane_moments.sort(key=lambda item: item["from_minute"])
    
        opponent_name = (opponent_identity or {}).get("riot_id") or "동일 포지션 상대"
        comparison_lines = []
        for item in lane_moments:
            comparison_lines.append(
                f"🔴 **{item['from_minute']} → {item['to_minute']}분 · 상대가 크게 이득**\n"
                f"└ 📊 AI 격차 `{item['score_gap_before']:+.1f} → {item['score_gap_after']:+.1f}` "
                f"(**{item['score_swing']:+.1f}**)\n"
                f"└ 💰 {gold_gap_delta_text(item['gold_gap_before'], item['gold_gap_after'])} "
                f"(**{item['gold_swing']:+,}G**)\n"
                f"└ ✨ 현재 XP `{item['xp_gap_after']:+,}` · 🌾 라인CS `{item['cs_gap_after']:+d}`"
            )
    
        timeline_file = None
        if plt and all_checkpoint_rows:
            try:
                target_points = [
                    (minute, float(row.get("checkpoint_score") or 0))
                    for minute, row, _frame in all_checkpoint_rows
                ]
    
                opponent_points = []
                if opponent_id:
                    for minute, _row, frame in all_checkpoint_rows:
                        opp_row = next(
                            (
                                item for item in frame.get("players", [])
                                if int(item.get("participant_id", 0)) == int(opponent_id)
                            ),
                            None,
                        )
                        if opp_row and opp_row.get("checkpoint_score") is not None:
                            opponent_points.append(
                                (minute, float(opp_row["checkpoint_score"]))
                            )
    
                # Team colors for the lane-score chart.
                # Blue-team player = blue line / red opponent.
                # Red-team player = red line / blue opponent.
                if target_team == "blue":
                    player_color = "#2f80ed"
                    opponent_color = "#e74c3c"
                else:
                    player_color = "#e74c3c"
                    opponent_color = "#2f80ed"
    
                fig, (ax1, ax2) = plt.subplots(
                    2, 1,
                    figsize=(8.8, 6.1),
                    dpi=120,
                    sharex=True,
                    gridspec_kw={"height_ratios": [1.15, 1.0]},
                )
    
                # ------------------------------------------------------------
                # Top graph: Player vs same-role lane opponent.
                # Keep ALL chart text ASCII/English to avoid missing Korean glyphs
                # on minimal Linux/Render matplotlib font installations.
                # ------------------------------------------------------------
                tx, ty = zip(*target_points)
                ax1.plot(
                    tx, ty,
                    linewidth=2.6,
                    marker="o",
                    markersize=3.3,
                    color=player_color,
                    label="Player",
                )
    
                if opponent_points:
                    ox, oy = zip(*opponent_points)
                    ax1.plot(
                        ox, oy,
                        linewidth=2.1,
                        marker="o",
                        markersize=3.0,
                        color=opponent_color,
                        label="Lane Opponent",
                    )
    
                ax1.axhline(
                    50,
                    linewidth=1.1,
                    linestyle="--",
                    color="#7f8c8d",
                    alpha=0.8,
                )
                ax1.text(
                    tx[0],
                    50.8,
                    "50 = even lane state",
                    fontsize=8.5,
                    va="bottom",
                    color="#555555",
                )
    
                if biggest_drop:
                    ax1.axvspan(
                        biggest_drop["from_minute"],
                        biggest_drop["to_minute"],
                        color="#e74c3c",
                        alpha=0.08,
                    )
                if biggest_rise:
                    ax1.axvspan(
                        biggest_rise["from_minute"],
                        biggest_rise["to_minute"],
                        color="#2ecc71",
                        alpha=0.06,
                    )
    
                ax1.set_title("AI Score - Player vs Lane Opponent")
                ax1.set_ylabel("AI Score")
                ax1.grid(True, linestyle="--", alpha=0.20)
                ax1.legend(loc="best")
    
                # ------------------------------------------------------------
                # Bottom graph: YOUR TEAM gold gap vs enemy team.
                # Positive = your team ahead = blue bar.
                # Negative = your team behind = red bar.
                # Both graphs share the exact same x-axis/minute scale.
                # ------------------------------------------------------------
                if team_flow:
                    gx = [item["minute"] for item in team_flow]
                    gy = [item["gold_gap"] for item in team_flow]
                    bar_colors = [
                        "#2f80ed" if value >= 0 else "#e74c3c"
                        for value in gy
                    ]
    
                    ax2.bar(
                        gx,
                        gy,
                        width=0.74,
                        color=bar_colors,
                        edgecolor="none",
                    )
                    ax2.axhline(
                        0,
                        linewidth=1.1,
                        color="#555555",
                    )
    
                    # Mark the strongest team-gold loss interval without Korean text.
                    if biggest_team_loss:
                        ax2.axvspan(
                            biggest_team_loss["from_minute"],
                            biggest_team_loss["to_minute"],
                            color="#e74c3c",
                            alpha=0.08,
                        )
    
                    ax2.set_ylabel("Your Team Gold Gap")
                    ax2.grid(True, axis="y", linestyle="--", alpha=0.20)
    
                ax2.set_title("Team Gold Gap - Same Time Axis")
                ax2.set_xlabel("Game Time (min)")
    
                # Make the shared time scale visually explicit.
                all_minutes = [minute for minute, _row, _frame in all_checkpoint_rows]
                if all_minutes:
                    min_m = min(all_minutes)
                    max_m = max(all_minutes)
                    step = 1 if (max_m - min_m) <= 20 else 2
                    ticks = list(range(min_m, max_m + 1, step))
                    ax2.set_xticks(ticks)
                    ax2.set_xlim(min_m - 0.5, max_m + 0.5)
    
                fig.tight_layout()
    
                image = io.BytesIO()
                fig.savefig(image, format="png", bbox_inches="tight")
                plt.close(fig)
                image.seek(0)
                timeline_file = discord.File(
                    image,
                    filename="rofl_ai_score_flow.png",
                )
                embed.set_image(url="attachment://rofl_ai_score_flow.png")
            except Exception as exc:
                logger.warning("ROFL flow graph render failed: %s", exc)
    
        # Page 1: personal + team flow.
        embed.set_footer(
            text="1 / 2 · 1분 단위 replay keyframe 기준 · 다음: 맞라이너 분석"
        )
    
        # Page 2: lane-opponent analysis only, so the long team-flow page stays readable.
        lane_embed = discord.Embed(
            title=f"⚔️ 맞라이너 분석 - {patch_label}",
            description=(
                f"🎮 **{participant.get('riot_id') or 닉네임태그}**  vs  "
                f"**{opponent_name}**\n"
                f"🏹 `{participant.get('role', '미지정')}` · **{participant.get('champion', '')}**"
            ),
            color=0x3498db if target_team == "blue" else 0xe74c3c,
        )
        if comparison_lines:
            lane_embed.add_field(
                name="📌 상대가 크게 이득 본 구간",
                value="\n\n".join(comparison_lines),
                inline=False,
            )
        else:
            lane_embed.add_field(
                name="📌 상대가 크게 이득 본 구간",
                value="뚜렷하게 급격한 우위를 만든 구간이 없습니다.",
                inline=False,
            )
        lane_embed.set_footer(
            text="2 / 2 · AI/골드 격차가 빠르게 상대 쪽으로 움직인 구간 중심"
        )
    
        class AIFlowPager(discord.ui.View):
            def __init__(self, owner_id: int):
                super().__init__(timeout=900)
                self.owner_id = int(owner_id)
                self.page = 0
                self._sync_buttons()
    
            def _sync_buttons(self):
                self.prev_page.disabled = self.page == 0
                self.next_page.disabled = self.page == 1
    
            async def interaction_check(self, button_interaction: discord.Interaction) -> bool:
                if int(button_interaction.user.id) != self.owner_id:
                    await button_interaction.response.send_message(
                        "이 분석을 실행한 사용자만 페이지를 넘길 수 있습니다.",
                        ephemeral=True,
                    )
                    return False
                return True
    
            @discord.ui.button(label="◀ 경기 흐름", style=discord.ButtonStyle.secondary)
            async def prev_page(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                self.page = 0
                self._sync_buttons()
                await button_interaction.response.edit_message(embed=embed, view=self)
    
            @discord.ui.button(label="맞라이너 분석 ▶", style=discord.ButtonStyle.primary)
            async def next_page(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                self.page = 1
                self._sync_buttons()
                await button_interaction.response.edit_message(embed=lane_embed, view=self)
    
        pager = AIFlowPager(interaction.user.id)
        if timeline_file:
            await interaction.followup.send(
                embed=embed,
                file=timeline_file,
                view=pager,
                ephemeral=True,
            )
        else:
            await interaction.followup.send(embed=embed, view=pager, ephemeral=True)
    
    
    MATCH_ANALYSIS_PERMISSION_KEY = "_match_analysis_permission"
    MATCH_ANALYSIS_ROLE_KEY = "_match_analysis_role_id"

    def get_match_analysis_permission(gid):
        guild_data = bot.user_data.setdefault(str(gid), {})
        value = str(guild_data.get(MATCH_ANALYSIS_PERMISSION_KEY) or "owner").strip().lower()
        if value not in {"owner", "administrator", "match_admin", "role", "everyone"}:
            return "owner"
        return value

    def can_use_match_analysis(interaction):
        # Bot owner always keeps an emergency bypass regardless of server setting.
        if is_bot_owner(interaction):
            return True

        guild = getattr(interaction, "guild", None)
        member = getattr(interaction, "user", None)
        if guild is None or member is None:
            return False

        gid = str(getattr(interaction, "guild_id", "") or "")
        permission = get_match_analysis_permission(gid)

        if permission == "owner":
            return False

        if permission == "administrator":
            return bool(getattr(getattr(member, "guild_permissions", None), "administrator", False))

        if permission == "match_admin":
            return bool(is_match_admin(interaction))

        if permission == "role":
            role_id = str(bot.user_data.setdefault(gid, {}).get(MATCH_ANALYSIS_ROLE_KEY) or "")
            if not role_id.isdigit():
                return False
            return any(str(getattr(role, "id", "")) == role_id for role in getattr(member, "roles", []))

        if permission == "everyone":
            return True

        return False

    def format_match_analysis_permission_denied(interaction):
        gid = str(getattr(interaction, "guild_id", "") or "")
        permission = get_match_analysis_permission(gid)
        labels = {
            "owner": "봇 오너",
            "administrator": "서버 관리자",
            "match_admin": "내전 관리자",
            "role": "지정 역할",
            "everyone": "전체 사용자",
        }
        label = labels.get(permission, "허용된 사용자")
        if permission == "role":
            role_id = str(bot.user_data.setdefault(gid, {}).get(MATCH_ANALYSIS_ROLE_KEY) or "")
            role = interaction.guild.get_role(int(role_id)) if interaction.guild and role_id.isdigit() else None
            if role:
                label = role.mention
        return f"🚫 경기분석 사용 권한이 없습니다. 현재 사용 가능 대상: **{label}**"

    @bot.tree.command(name="경기분석", description="ROFL을 개인 또는 블루/레드 팀 기준으로 분석합니다.")
    @app_commands.describe(분석대상="팀 분석: 블루/레드 · 개인 분석: 닉네임 또는 닉네임#태그")
    async def rofl_match_analysis(
        interaction: discord.Interaction,
        파일: discord.Attachment,
        분석대상: str,
    ):
        _sync_runtime()
        get_rofl_champion_map = runtime["get_rofl_champion_map"]
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
        except discord.NotFound:
            logger.warning("Match analysis interaction expired before defer.")
            return
    
        if not can_use_match_analysis(interaction):
            return await interaction.followup.send(
                format_match_analysis_permission_denied(interaction),
                ephemeral=True,
            )
        if not str(파일.filename or "").lower().endswith(".rofl"):
            return await interaction.followup.send("⚠️ `.rofl` 리플레이 파일만 업로드해주세요.", ephemeral=True)
    
        try:
            report = await load_match_analysis_context(
                interaction,
                파일,
                분석대상,
                helper_scope={
                    "get_rofl_champion_map": get_rofl_champion_map,
                    "validate_rofl_upload_size": validate_rofl_upload_size,
                    "run_rofl_analysis_once": run_rofl_analysis_once,
                    "normalize_rofl_match_name": normalize_rofl_match_name,
                    "resolve_rofl_input_riot_id": resolve_rofl_input_riot_id,
                },
            )
            await send_match_analysis_pages(
                interaction,
                report.pages,
                report.page_labels,
                report.player_name,
                report.patch_display_label,
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⚠️ 경기 분석이 75초를 초과해 중단되었습니다.",
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("ROFL match analysis failed")
            await interaction.followup.send(
                f"⚠️ 경기 분석 실패: `{str(exc)[:900]}`",
                ephemeral=True,
            )

    @rofl_match_analysis.autocomplete("분석대상")
    async def rofl_match_analysis_target_autocomplete(interaction: discord.Interaction, current: str):
        current_norm = str(current or "").strip().lower()
        choices = [
            app_commands.Choice(name="🔵 블루팀 전체 분석", value="블루"),
            app_commands.Choice(name="🔴 레드팀 전체 분석", value="레드"),
        ]
        if not current_norm:
            return choices
        return [choice for choice in choices if current_norm in choice.name.lower() or current_norm in choice.value.lower()]
    
    
    class MatchAnalysisTestView(discord.ui.View):
        """Owner-only UI preview for every role's match-analysis layout.
    
        Test values are generated in-memory for this view only. They are never
        written to match history, MMR, replay stats, or any persistent store.
        """
    
        ROLE_META = {
            "탑": ("⚔️", "요네", ("🌱 초반", "⚔️ 주요 교전", "🧠 승부 포인트", "📋 총정리")),
            "정글": ("🌲", "리 신", ("🌱 초반", "⚔️ 주요 교전", "🧠 승부 포인트", "📋 총정리")),
            "미드": ("⚡", "아리", ("🌱 초반", "⚔️ 주요 교전", "🧠 승부 포인트", "📋 총정리")),
            "원딜": ("🏹", "징크스", ("🌱 초반", "⚔️ 주요 교전", "🧠 승부 포인트", "📋 총정리")),
            "서폿": ("💫", "쓰레쉬", ("🌱 초반", "⚔️ 주요 교전", "🧠 승부 포인트", "📋 총정리")),
        }
    
        def __init__(self, owner_id: int):
            super().__init__(timeout=3600)
            self.owner_id = int(owner_id)
            self.role = "탑"
            self.page = 0
            self.seed = random.randint(100_000, 999_999)
            self.pages_by_role = {
                role: self._build_role_pages(role, random.Random(self.seed + index * 7919))
                for index, role in enumerate(self.ROLE_META)
            }
    
            options = [
                discord.SelectOption(label=role, value=role, emoji=meta[0], default=(role == self.role))
                for role, meta in self.ROLE_META.items()
            ]
            self.role_select = discord.ui.Select(
                placeholder="포지션 선택",
                min_values=1,
                max_values=1,
                options=options,
                row=0,
            )
            self.role_select.callback = self._role_changed
            self.add_item(self.role_select)
            self._sync_buttons()
    
        def _rand_time(self, rng, low=4, high=27):
            minute = rng.randint(low, high)
            second = rng.randint(0, 59)
            return f"{minute}분 {second:02d}초"
    
        def _base_embed(self, role, champion):
            icon = self.ROLE_META[role][0]
            embed = discord.Embed(
                title="테스트유저#TEST 리포트 - 26.17 패치",
                description=f"🧪 **테스트 데이터** · 실제 기록/점수에는 저장되지 않습니다.\n{icon} `{role}` · **{champion}**",
                color=0x5865F2,
            )
            return embed
    
        def _build_role_pages(self, role, rng):
            _icon, champion, labels = self.ROLE_META[role]
            pages = [self._base_embed(role, champion) for _ in range(4)]
            opponent = {"탑":"신지드", "정글":"그레이브즈", "미드":"오리아나", "원딜":"카이사", "서폿":"노틸러스"}[role]
            matchup = f"⚔️ **{role} · {champion} vs {opponent}**"

            # Page 1: role-specific early cutoff, same compact visual grammar.
            pages[0].title = f"🌱 {role} 초반 - 26.17 패치"
            pages[0].description = matchup
            if role in {"탑", "원딜", "서폿"}:
                my_q = {"탑":"11분 32초", "원딜":"12분 18초", "서폿":"14분 06초"}[role]
                opp_q = {"탑":"12분 52초", "원딜":"13분 01초", "서폿":"13분 44초"}[role]
                cutoff = max(my_q, opp_q)
                pages[0].add_field(name="⏱️ 초반 종료 기준", value=f"**{cutoff}** · 나 `{my_q}` / 상대 `{opp_q}` 퀘스트 완료", inline=False)
            else:
                pages[0].add_field(name="⏱️ 초반 종료 기준", value="**13분 08초** · 경기 첫 1차 포탑 파괴 (미드)", inline=False)
            if role == "정글":
                growth = "**우세** · 💰 골드 `+420G` · ⬆️ 레벨 `9 vs 8` · 🌲 정글 CS `+11`"
            elif role == "서폿":
                growth = "**비슷** · 💰 골드 `+110G` · ⬆️ 레벨 `8 vs 8`"
            else:
                growth = "**우세** · 💰 골드 `+850G` · ⬆️ 레벨 `10 vs 9` · 🌾 CS `+14`"
            pages[0].add_field(name="📊 종료 시점 성장 격차", value=growth, inline=False)
            pages[0].set_footer(text="1 / 4 · 초반")

            # Page 2: only notable fights.
            pages[1].title = f"⚔️ {role} 주요 교전 - 26.17 패치"
            pages[1].description = matchup + "\n초반 종료 이후 · 복기 가치가 큰 장면만 표시"
            damage = "" if role == "서폿" else "\n└ 💥 팀 교전딜 비중 **31%**"
            pages[1].add_field(
                name="🔥 복기할 교전",
                value=(
                    f"🟢 **18분 42초 · 3:1 승리** · 드래곤 인접\n└ 본인 `1/0/2`{damage}\n└ 💰 팀 골드차 `-620G → +480G`\n\n"
                    f"🔴 **24분 16초 · 1:3 패배**\n└ 본인 `0/1/1`{('' if role == '서폿' else chr(10)+'└ 💥 팀 교전딜 비중 **17%**')}\n└ 💰 팀 골드차 `+1,120G → -310G`"
                ), inline=False,
            )
            pages[1].set_footer(text="2 / 4 · 주요 교전")

            # Page 3: consequence, not event log.
            pages[2].title = f"🧠 {role} 승부 포인트 - 26.17 패치"
            pages[2].description = matchup
            obj_extra = "\n  └ 본인 킬관여 `3` · 데스 `0`" if role == "서폿" else "\n  └ 본인 팀 교전딜 비중 **31%**"
            pages[2].add_field(
                name="🐉 오브젝트 교전",
                value=f"• **18분 51초 · 드래곤 획득**\n  └ 교전 `3:1` · 2분 골드차 `-620G → +1,340G`{obj_extra}",
                inline=False,
            )
            pages[2].add_field(
                name="💰 흐름을 크게 바꾼 교전",
                value="📈 **18분 42초** · 교전 시작 `-620G` → 2분 뒤 `+1,340G` (**+1,960G 변화**)",
                inline=False,
            )
            pages[2].add_field(
                name="🚨 내 데스로 크게 흔들린 지점",
                value="💀 **24분 16초 데스**\n  └ 팀 골드차 `+1,120G → -780G` · 바론 시야 주도권 및 미드 1차 손실",
                inline=False,
            )
            pages[2].set_footer(text="3 / 4 · 승부 포인트")

            pages[3].title = f"📋 {role} 총정리 - 26.17 패치"
            pages[3].description = matchup
            pages[3].add_field(name="🌱 초반", value=growth, inline=False)
            pages[3].add_field(name="✅ 가장 좋았던 전환", value="**18분 42초 드래곤 교전** 이후 2분 동안 팀 골드 흐름을 **+1,960G** 개선했습니다.", inline=False)
            pages[3].add_field(name="🛠️ 가장 먼저 복기할 장면", value="**24분 16초 데스** 이후 팀 골드 흐름이 크게 악화됐습니다. 사망 직전 위치와 진입 판단을 먼저 확인하세요.", inline=False)
            pages[3].set_footer(text="4 / 4 · 총정리")
            return pages

        def _sync_buttons(self):
            labels = self.ROLE_META[self.role][2]
            buttons = [self.page1, self.page2, self.page3, self.page4]
            for index, button in enumerate(buttons):
                button.label = labels[index]
                button.style = discord.ButtonStyle.primary if index == self.page else discord.ButtonStyle.secondary
            for option in self.role_select.options:
                option.default = option.value == self.role
    
        async def _render(self, interaction: discord.Interaction):
            self._sync_buttons()
            await interaction.response.edit_message(embed=self.pages_by_role[self.role][self.page], view=self)
    
        async def _role_changed(self, interaction: discord.Interaction):
            self.role = self.role_select.values[0]
            self.page = 0
            await self._render(interaction)
    
        @discord.ui.button(label="🌱 성장격차", style=discord.ButtonStyle.primary, row=1)
        async def page1(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page = 0
            await self._render(interaction)
    
        @discord.ui.button(label="📊 팀이득", style=discord.ButtonStyle.secondary, row=1)
        async def page2(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page = 1
            await self._render(interaction)
    
        @discord.ui.button(label="⚔️ 한타기여", style=discord.ButtonStyle.secondary, row=1)
        async def page3(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page = 2
            await self._render(interaction)
    
        @discord.ui.button(label="🩹 약점", style=discord.ButtonStyle.secondary, row=1)
        async def page4(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page = 3
            await self._render(interaction)
    
    
    @bot.tree.command(name="경기분석테스트", description="[봇 오너] 포지션별 경기분석 UI를 테스트 데이터로 확인합니다.")
    async def match_analysis_ui_test(interaction: discord.Interaction):
        if not is_bot_owner(interaction):
            return await interaction.response.send_message("🚫 봇 오너만 사용할 수 있습니다.", ephemeral=True)
        view = MatchAnalysisTestView(interaction.user.id)
        await interaction.response.send_message(
            embed=view.pages_by_role[view.role][0],
            view=view,
            ephemeral=True,
        )
    
    
    async def detail_stat_image_analyze(
        interaction: discord.Interaction,
        점수판: discord.Attachment,
        딜량그래프: discord.Attachment,
        순번: app_commands.Range[int, 1, 50] = 1,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 상세 스탯을 분석할 수 있습니다.", ephemeral=True)
        if not os.getenv("OPENAI_API_KEY"):
            return await interaction.response.send_message(
                "⚠️ 이미지 자동 분석에는 `OPENAI_API_KEY` 환경변수가 필요합니다. "
                "누락 값은 `/리플레이기록`으로 ROFL 파일을 다시 올려 보완할 수 있습니다.",
                ephemeral=True
            )
    
        gid = str(interaction.guild_id)
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
        if len(records) < 순번:
            return await interaction.response.send_message(
                f"⚠️ 확인 가능한 경기 기록은 {len(records)}개입니다.",
                ephemeral=True
            )
    
        await interaction.response.defer(thinking=True)
        record = records[순번 - 1]
        try:
            image_payloads = [
                await attachment_to_data_url(점수판),
                await attachment_to_data_url(딜량그래프),
            ]
            prompt = build_detail_stat_analysis_prompt(interaction.guild, gid, record)
            analysis = await asyncio.to_thread(call_openai_vision_sync, prompt, image_payloads)
        except Exception as exc:
            return await interaction.followup.send(f"⚠️ 이미지 분석 실패: `{str(exc)[:900]}`", ephemeral=True)
    
        duration_seconds = match_stats.parse_duration_seconds(analysis.get("duration") or record.get("duration"))
        if duration_seconds <= 0:
            duration_seconds = match_stats.parse_duration_seconds("1:00")
    
        guild_data = bot.user_data.setdefault(gid, {})
        entries = []
        warnings = []
        for raw in analysis.get("entries", []):
            uid = str(raw.get("user_id", "")).strip()
            player = match_stats.find_player_record(record, uid)
            if not player:
                warnings.append(f"매칭 실패: `{raw.get('screenshot_name', '이름 없음')}`")
                continue
            opponent = get_opponent_player_record(record, player)
            team = player.get("team", "")
            team_kills = int(analysis.get("blue_team_kills", 0) if team == "blue" else analysis.get("red_team_kills", 0))
            try:
                entry = match_stats.build_entry(
                    match_id=record.get("id"),
                    user_id=uid,
                    champion=raw.get("champion", ""),
                    role=player.get("role", "미지정"),
                    team=team,
                    result=player.get("result", "unknown"),
                    kills=int(raw.get("kills", 0)),
                    deaths=int(raw.get("deaths", 0)),
                    assists=int(raw.get("assists", 0)),
                    cs=int(raw.get("cs", 0)),
                    gold=int(raw.get("gold", 0)),
                    damage=int(raw.get("damage", 0)),
                    duration_seconds=duration_seconds,
                    team_kills=team_kills,
                    before_mmr=player.get("before_mmr", 0),
                    opponent_mmr=opponent.get("before_mmr", 0) if opponent else 0,
                    screenshot_name=raw.get("screenshot_name", ""),
                    source="vision",
                )
            except (TypeError, ValueError):
                warnings.append(f"숫자 파싱 실패: `{raw.get('screenshot_name', uid)}`")
                continue
            entries.append(entry)
    
        preview_store = {}
        for entry in entries:
            match_stats.upsert_entry(preview_store, entry)
        preview_awards = match_stats.score_match_awards(preview_store, record.get("id"))
    
        embed = discord.Embed(
            title="🧪 상세 스탯 이미지 분석 결과",
            description=(
                f"경기: **최근 {순번}번째 경기** (`{record.get('id')}`)\n"
                f"분석 인원: **{len(entries)}명** / 경기시간 **{match_stats.format_duration(duration_seconds)}**\n"
                "아래 결과를 확인한 뒤 저장해 주세요."
            ),
            color=0x9b59b6
        )
        lines = []
        for entry in entries[:10]:
            name = get_member_display_name(interaction.guild, gid, entry["user_id"])
            lines.append(
                f"**{name}** `{entry['role']}` {entry.get('champion') or '챔피언 미확정'} "
                f"{entry['kills']}/{entry['deaths']}/{entry['assists']} "
                f"CS {entry['cs']} DMG {entry['damage']:,} 킬 관여율 {entry['kill_participation']:.1f}%"
            )
        embed.add_field(name="추출된 상세 스탯", value="\n".join(lines) if lines else "매칭된 데이터 없음", inline=False)
        embed.add_field(name="MVP 후보", value=format_award_line(interaction.guild, gid, preview_awards.get("mvp")), inline=False)
        embed.add_field(name="ACE 후보", value=format_award_line(interaction.guild, gid, preview_awards.get("ace")), inline=False)
        if warnings:
            embed.add_field(name="확인 필요", value="\n".join(warnings[:8]), inline=False)
    
        view = DetailStatConfirmView(gid, record, entries, str(interaction.user.id))
        await interaction.followup.send(embed=embed, view=view)
    
    async def screenshot_champion_test(
        interaction: discord.Interaction,
        점수판: discord.Attachment,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 테스트할 수 있습니다.", ephemeral=True)
    
        await interaction.response.defer(thinking=True)
        try:
            image_bytes = await 점수판.read()
            results = await asyncio.to_thread(screenshot_stats.analyze_scoreboard_champions, image_bytes, 3)
        except Exception as exc:
            return await interaction.followup.send(f"⚠️ 챔피언 매칭 실패: `{str(exc)[:900]}`", ephemeral=True)
    
        lines = []
        for result in results:
            candidates = result.get("candidates", [])
            if not candidates:
                lines.append(f"**{result['label']}**: 후보 없음")
                continue
            best = candidates[0]
            alternatives = ", ".join(
                f"{candidate['name']}({candidate['score']})"
                for candidate in candidates[1:]
            )
            suffix = f" | 후보: {alternatives}" if alternatives else ""
            lines.append(f"**{result['label']}**: **{best['name']}** `{best['score']}`{suffix}")
    
        embed = discord.Embed(
            title="🧪 스샷 챔피언 매칭 테스트",
            description="\n".join(lines),
            color=0x9b59b6
        )
        embed.set_footer(text="낮은 점수일수록 초상화가 더 비슷하다는 뜻입니다. 이 결과는 저장되지 않습니다.")
        await interaction.followup.send(embed=embed)
    
    async def screenshot_scoreboard_test(
        interaction: discord.Interaction,
        점수판: discord.Attachment,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 테스트할 수 있습니다.", ephemeral=True)
    
        await interaction.response.defer(thinking=True)
        try:
            scoreboard_bytes = await 점수판.read()
            champion_rows, scoreboard_rows, match_duration = await asyncio.gather(
                asyncio.to_thread(screenshot_stats.analyze_scoreboard_champions, scoreboard_bytes, 3),
                asyncio.to_thread(screenshot_stats.ocr_scoreboard_core_numbers, scoreboard_bytes),
                asyncio.to_thread(screenshot_stats.ocr_match_duration, scoreboard_bytes),
            )
            crop_sheet, crop_meta = await asyncio.to_thread(screenshot_stats.build_scoreboard_debug_crop_sheet, scoreboard_bytes)
        except Exception as exc:
            return await interaction.followup.send(f"⚠️ 점수판 분석 실패: `{str(exc)[:900]}`", ephemeral=True)
    
        champion_by_row = {
            row: result
            for row, result in enumerate(champion_rows, 1)
        }
        lines = []
        for row in scoreboard_rows:
            row_no = row["row"]
            champion_result = champion_by_row.get(row_no, {})
            candidates = (champion_result.get("candidates") or [])[:3]
            if candidates:
                champion_text = ", ".join(
                    f"{candidate.get('name', '확인필요')} `{candidate.get('score')}`"
                    for candidate in candidates
                )
            else:
                champion_text = "챔피언 확인필요"
            kda = row.get("kda")
            kda_text = f"{kda[0]}/{kda[1]}/{kda[2]}" if kda else f"확인필요({', '.join(row.get('kda_candidates', []))})"
            lines.append(f"**{row_no}줄** 후보 {champion_text} | KDA `{kda_text}`")
    
        meta_text = ""
        if crop_meta:
            size = crop_meta.get("size") or ("?", "?")
            meta_text = f"\n레이아웃: `{crop_meta.get('layout')}` / 크기: `{size[0]}x{size[1]}`"
        embed = discord.Embed(
            title="🧪 스샷 점수판 테스트",
            description=f"경기 시간: `{match_duration or '확인필요'}`{meta_text}\n\n" + "\n".join(lines),
            color=0x9b59b6
        )
        embed.set_footer(text="챔피언 점수는 낮을수록 더 비슷합니다. 첨부 이미지는 봇이 실제로 잘라본 챔피언/KDA 위치입니다.")
        file = discord.File(io.BytesIO(crop_sheet), filename="scoreboard_debug_crops.png")
        await interaction.followup.send(embed=embed, file=file)
    
    async def screenshot_damage_test(
        interaction: discord.Interaction,
        딜량그래프: discord.Attachment,
        전체분석: bool = False,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 테스트할 수 있습니다.", ephemeral=True)
    
        await interaction.response.defer(thinking=True)
        try:
            damage_bytes = await 딜량그래프.read()
            if 전체분석:
                damage_rows = await asyncio.to_thread(screenshot_stats.ocr_damage_numbers, damage_bytes)
            else:
                damage_rows = await asyncio.to_thread(screenshot_stats.ocr_damage_numbers_fast, damage_bytes)
        except Exception as exc:
            return await interaction.followup.send(f"⚠️ 딜량 OCR 실패: `{str(exc)[:900]}`", ephemeral=True)
    
        lines = []
        for row in damage_rows:
            candidates = row.get("damage_candidates", [])
            suffix = f" | 후보 `{', '.join(str(value) for value in candidates)}`" if 전체분석 and candidates else ""
            lines.append(f"**{row['row']}줄** 딜량 `{row.get('damage', 0):,}`{suffix}")
    
        embed = discord.Embed(
            title="🧪 스샷 딜량 테스트",
            description=f"모드: `{'전체 분석' if 전체분석 else '빠른 분석'}`\n\n" + "\n".join(lines),
            color=0x3498db
        )
        embed.set_footer(text="막대 끝 오른쪽 숫자 라벨만 잘라 읽습니다. 이 결과는 저장되지 않습니다.")
        await interaction.followup.send(embed=embed)
    
    async def screenshot_number_test(
        interaction: discord.Interaction,
        점수판: discord.Attachment,
        딜량그래프: discord.Attachment,
        전체분석: bool = False,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 테스트할 수 있습니다.", ephemeral=True)
    
        await interaction.response.defer(thinking=True)
        try:
            scoreboard_bytes = await 점수판.read()
            damage_bytes = await 딜량그래프.read()
            match_duration = await asyncio.to_thread(screenshot_stats.ocr_match_duration, scoreboard_bytes)
            if 전체분석:
                scoreboard_rows = await asyncio.to_thread(screenshot_stats.ocr_scoreboard_numbers, scoreboard_bytes)
                damage_rows = await asyncio.to_thread(screenshot_stats.ocr_damage_numbers, damage_bytes)
            else:
                scoreboard_rows = await asyncio.to_thread(screenshot_stats.ocr_scoreboard_core_numbers, scoreboard_bytes)
                damage_rows = await asyncio.to_thread(screenshot_stats.ocr_damage_numbers_fast, damage_bytes)
        except Exception as exc:
            return await interaction.followup.send(f"⚠️ 숫자 OCR 실패: `{str(exc)[:900]}`", ephemeral=True)
    
        damage_by_row = {row["row"]: row for row in damage_rows}
        lines = []
        for row in scoreboard_rows:
            kda = row.get("kda")
            kda_text = f"{kda[0]}/{kda[1]}/{kda[2]}" if kda else f"확인필요({', '.join(row.get('kda_candidates', []))})"
            damage = damage_by_row.get(row["row"], {}).get("damage", 0)
            if 전체분석:
                lines.append(
                    f"**{row['row']}줄** KDA `{kda_text}` | 딜량 `{damage:,}`"
                )
            else:
                lines.append(f"**{row['row']}줄** KDA `{kda_text}` | 딜량 `{damage:,}`")
    
        embed = discord.Embed(
            title="🧪 스샷 숫자 OCR 테스트",
            description=(
                f"모드: `{'전체 분석' if 전체분석 else '빠른 분석'}`\n"
                f"경기 시간: `{match_duration or '확인필요'}`\n\n"
                + "\n".join(lines)
            ),
            color=0x3498db
        )
        embed.set_footer(text="KDA/딜량만 확인합니다. 이 결과는 저장되지 않습니다.")
        await interaction.followup.send(embed=embed)
    
    async def detail_stat_summary(interaction: discord.Interaction, 보기: str = "", 유저: discord.Member = None):
        gid = str(interaction.guild_id)
        target = 유저 or interaction.user
        guild_data = bot.user_data.setdefault(gid, {})
        detail_view = normalize_record_detail_view(보기)
        role = detail_view[1] if detail_view and detail_view[0] == "role" else None
        if 보기 and not role:
            return await interaction.response.send_message("⚠️ 상세스탯 보기는 `탑`, `정글`, `미드`, `원딜`, `서폿` 중 하나로 입력해 주세요.", ephemeral=True)
    
        row = aggregate_detail_entries(guild_data, user_id=str(target.id), role=role)
        if not row:
            empty = f"📭 아직 `{role}` 라인 상세 스탯이 없습니다." if role else "📭 아직 기록된 상세 스탯이 없습니다."
            return await interaction.response.send_message(empty, ephemeral=True)
    
        champion_rows = aggregate_detail_entries(guild_data, user_id=str(target.id), role=role, group_key="champion")
        title = f"📊 {target.display_name} {role} 상세 스탯" if role else f"📊 {target.display_name} 상세 스탯"
        embed = build_detail_summary_embed(title, row, champion_rows, role=role, guild=interaction.guild)
        await interaction.response.send_message(embed=embed)
    
    async def detail_stat_mvp(interaction: discord.Interaction, 순번: app_commands.Range[int, 1, 50] = 1):
        gid = str(interaction.guild_id)
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
        if len(records) < 순번:
            return await interaction.response.send_message(
                f"⚠️ 확인 가능한 경기 기록은 {len(records)}개입니다.",
                ephemeral=True
            )
        record = records[순번 - 1]
        guild_data = bot.user_data.setdefault(gid, {})
        _, entry_count = match_stats.summarize_entries_count(guild_data)
        awards = match_stats.score_match_awards(guild_data, record.get("id"))
        if not awards.get("scores"):
            return await interaction.response.send_message("📭 이 경기에는 아직 상세 스탯이 저장되지 않았습니다.", ephemeral=True)
        embed = build_match_awards_embed(interaction.guild, gid, record.get("id"))
        embed.description = f"경기: **최근 {순번}번째 경기** (`{record.get('id')}`) | 전체 상세 기록 {entry_count}개"
        await interaction.response.send_message(embed=embed)
    
    def is_detail_stat_trackable_record(record):
        if not record:
            return False
        mode = record.get("mode", "classic")
        if mode not in ("classic", LOW_TIER_MODE_KEY, NOBAN_MODE_KEY, LEAGUE_MODE_KEY, LEAGUE_SERIES_MODE_KEY):
            return False
        players = record.get("players", []) or []
        return isinstance(players, list) and len(players) >= 10
    
    def add_chunked_embed_fields(embed, title, lines, *, max_chars=900, inline=False):
        chunk = []
        chunk_len = 0
        field_no = 1
        safe_lines = [
            part
            for line in lines
            for part in (
                [str(line)[index:index + max_chars] for index in range(0, len(str(line)), max_chars)]
                or [""]
            )
        ]
        for line in safe_lines:
            line_len = len(line) + 2
            if chunk and chunk_len + line_len > max_chars:
                suffix = " · 계속" if field_no > 1 else ""
                embed.add_field(name=f"{title}{suffix}", value="\n\n".join(chunk), inline=inline)
                field_no += 1
                chunk = []
                chunk_len = 0
            chunk.append(line)
            chunk_len += line_len
        if chunk:
            suffix = " · 계속" if field_no > 1 else ""
            embed.add_field(name=f"{title}{suffix}", value="\n\n".join(chunk), inline=inline)
    
    def safe_detail_int(value, default=0):
        try:
            if value in (None, ""):
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default
    
    def safe_detail_float(value, default=0.0):
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default
    
    def format_detail_missing_record_line(guild, gid, rank, record, saved_count):
        match_id = str(record.get("id") or record.get("match_id") or f"rank-{rank}")
        when = record.get("time", "시간 미상")
        players = record.get("players", []) or []
        missing_players = []
        saved_entries = match_stats.get_store(bot.user_data.setdefault(gid, {})).get(match_id, {})
        for player in players[:10]:
            if not isinstance(player, dict):
                continue
            uid = str(player.get("user_id"))
            if not uid or uid == "None":
                continue
            if uid not in saved_entries:
                missing_players.append(get_member_display_name(guild, gid, uid))
        missing_text = ", ".join(missing_players[:4])
        if len(missing_players) > 4:
            missing_text += f" 외 {len(missing_players) - 4}명"
        if not missing_text:
            missing_text = "저장 인원 부족"
        return (
            f"`{rank}` 최근 {rank}번째 경기 · `{when}`\n"
            f"└ 저장 **{saved_count}/10명** · ID `{match_id}` · 누락: {missing_text}"
        )
    
    DETAIL_STAT_MISSING_CUTOFF = datetime(2026, 6, 25, 0, 0, 0)
    DETAIL_STAT_MISSING_CUTOFF_KEY = "detail_stat_missing_cutoff"

    def get_saved_detail_missing_cutoff(guild_data):
        raw = str((guild_data or {}).get(DETAIL_STAT_MISSING_CUTOFF_KEY) or "").strip()
        if raw:
            parsed = parse_date_option(raw, default_year=DETAIL_STAT_MISSING_CUTOFF.year)
            if parsed:
                return parsed
        return DETAIL_STAT_MISSING_CUTOFF

    @app_commands.describe(
        최근경기수="확인할 상세스탯 대상 경기 수입니다.",
        기준날짜="입력하면 이 날짜를 서버 누락검사 시작일로 저장합니다. 이후에는 생략해도 유지됩니다. 예: 2026-08-25",
    )
    async def detail_stat_missing_check(
        interaction: discord.Interaction,
        최근경기수: app_commands.Range[int, 1, 100] = 30,
        기준날짜: str = "",
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message(
                "⚠️ 내전 관리자만 상세스탯 누락을 확인할 수 있습니다.",
                ephemeral=True,
            )

        gid = str(interaction.guild_id)
        guild_data = bot.user_data.setdefault(gid, {})
        cutoff_updated = False

        if str(기준날짜 or "").strip():
            cutoff = parse_date_option(
                기준날짜,
                default_year=DETAIL_STAT_MISSING_CUTOFF.year,
            )
            if not cutoff:
                return await interaction.response.send_message(
                    "⚠️ 기준날짜 형식을 확인해주세요. 예: `2026-08-25`, `8/25`, `0825`",
                    ephemeral=True,
                )
            guild_data[DETAIL_STAT_MISSING_CUTOFF_KEY] = cutoff.strftime("%Y-%m-%d")
            bot.save_lucid_data(gid)
            cutoff_updated = True
        else:
            cutoff = get_saved_detail_missing_cutoff(guild_data)

        detail_store = match_stats.get_store(guild_data)
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
    
        checked = 0
        missing = []
        for rank, record in enumerate(records, 1):
            if checked >= 최근경기수:
                break
            record_time = parse_history_time(record)
            if not record_time or record_time < cutoff:
                continue
            if not is_detail_stat_trackable_record(record):
                continue
            checked += 1
            match_id = str(record.get("id"))
            saved_count = len(detail_store.get(match_id, {}) or {})
            if saved_count < 10:
                missing.append((rank, record, saved_count))
    
        embed = discord.Embed(title="🧾 상세스탯 누락 확인", color=0xe67e22 if missing else 0x2ecc71)
        cutoff_label = cutoff.strftime("%Y-%m-%d")
        setting_note = " · **서버 기준일로 저장됨**" if cutoff_updated else " · 저장된 서버 기준일"
        embed.description = (
            f"기준일 **`{cutoff_label}`**{setting_note}\n"
            f"이 날짜 이후 상세스탯 대상 경기 **{checked}개**를 확인했습니다."
        )
    
        if not missing:
            embed.add_field(name="결과", value="✅ 누락된 상세스탯 기록이 없습니다.", inline=False)
        else:
            lines = [
                format_detail_missing_record_line(interaction.guild, gid, rank, record, saved_count)
                for rank, record, saved_count in missing[:10]
            ]
            add_chunked_embed_fields(embed, f"누락 경기 {len(missing)}개", lines)
            if len(missing) > 10:
                embed.set_footer(text=f"상위 10개만 표시했습니다. 최근경기수 값을 줄이거나 경기기록 순번으로 확인하세요.")
            else:
                embed.set_footer(text="누락된 경기는 /리플레이기록으로 ROFL 파일을 올려 보완할 수 있습니다.")
    
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    class ReplayDetailCancelConfirmView(discord.ui.View):
        def __init__(self, *, requester_id: int, gid: str, match_id: str, rank: int):
            super().__init__(timeout=60)
            self.requester_id = int(requester_id)
            self.gid = str(gid)
            self.match_id = str(match_id)
            self.rank = int(rank)
            self.finished = False
    
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.requester_id:
                await interaction.response.send_message("⚠️ 이 확인 버튼은 명령어를 실행한 관리자만 사용할 수 있습니다.", ephemeral=True)
                return False
            return True
    
        @discord.ui.button(label="리플레이 기록 취소", style=discord.ButtonStyle.danger, custom_id="lucid:replay_detail_cancel:confirm")
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            _sync_runtime()
            guild_data = bot.user_data.setdefault(self.gid, {})
            detail_store = match_stats.get_store(guild_data)
            match_entries = dict(detail_store.get(self.match_id, {}) or {})
            if not match_entries:
                self.finished = True
                self.stop()
                return await interaction.response.edit_message(
                    content="📭 이미 취소되었거나 삭제할 리플레이 상세기록이 없습니다.",
                    embed=None,
                    view=None,
                )
    
            await interaction.response.defer()
            removed_count = 0
            live_entries = detail_store.get(self.match_id, {}) or {}
            for uid, entry in list(live_entries.items()):
                if str((entry or {}).get("source") or "").lower() == "rofl":
                    live_entries.pop(uid, None)
                    removed_count += 1
            if not live_entries:
                detail_store.pop(self.match_id, None)
            if removed_count <= 0:
                self.finished = True
                self.stop()
                return await interaction.edit_original_response(
                    content="📭 이미 취소되었거나 삭제할 ROFL 상세기록이 없습니다.",
                    embed=None,
                    view=None,
                )
            guild_data.get(match_stats.AWARD_SNAPSHOTS_KEY, {}).pop(self.match_id, None)
            bot.save_lucid_data(self.gid)
            self.finished = True
            self.stop()
            embed = discord.Embed(
                title="🧹 리플레이 기록 취소 완료",
                description=(
                    f"최근 **{self.rank}번째 경기** (`{self.match_id}`)의 ROFL 상세기록 **{removed_count}명**을 삭제했습니다.\n"
                    "MMR, 승패, 기본 경기기록은 그대로 유지됩니다.\n"
                    "챔피언 통계, 상세스탯, MVP/ACE 집계에서 해당 리플레이 데이터만 제외됩니다."
                ),
                color=0xe74c3c,
            )
            await interaction.edit_original_response(embed=embed, view=None)
    
        @discord.ui.button(label="닫기", style=discord.ButtonStyle.secondary, custom_id="lucid:replay_detail_cancel:close")
        async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.finished = True
            self.stop()
            await interaction.response.edit_message(content="✅ 취소 작업을 중단했습니다.", embed=None, view=None)
    
    
    async def detail_stat_record_cancel(
        interaction: discord.Interaction,
        순번: app_commands.Range[int, 1, 50] = 1,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 리플레이 상세기록을 취소할 수 있습니다.", ephemeral=True)
    
        gid = str(interaction.guild_id)
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
        if len(records) < 순번:
            return await interaction.response.send_message(
                f"⚠️ 확인 가능한 경기 기록은 {len(records)}개입니다.",
                ephemeral=True,
            )
    
        record = records[순번 - 1]
        match_id = str(record.get("id"))
        guild_data = bot.user_data.setdefault(gid, {})
        detail_store = match_stats.get_store(guild_data)
        match_entries = dict(detail_store.get(match_id, {}) or {})
        if not match_entries:
            return await interaction.response.send_message(
                f"📭 최근 {순번}번째 경기에는 취소할 리플레이/상세스탯 기록이 없습니다.",
                ephemeral=True,
            )
    
        rofl_entries = [entry for entry in match_entries.values() if str(entry.get("source") or "").lower() == "rofl"]
        if not rofl_entries:
            return await interaction.response.send_message(
                f"📭 최근 {순번}번째 경기에는 ROFL로 저장된 상세기록이 없습니다.",
                ephemeral=True,
            )
    
        lines = []
        for entry in rofl_entries[:10]:
            name = get_member_display_name(interaction.guild, gid, entry.get("user_id"))
            lines.append(
                f"**{name}** `{entry.get('role')}` {entry.get('champion')} · "
                f"{entry.get('kills')}/{entry.get('deaths')}/{entry.get('assists')}"
            )
    
        when = record.get("time") or "시간 없음"
        winner = str(record.get("winner") or "").lower()
        winner_text = "블루 승" if winner == "blue" else "레드 승" if winner == "red" else "승리팀 미확인"
        embed = discord.Embed(
            title="⚠️ 리플레이 기록 취소 확인",
            description=(
                f"`/경기기록` 기준 최근 **{순번}번째 경기**의 ROFL 상세기록을 취소합니다.\n"
                f"경기 시간: **{when}** · **{winner_text}** · ID `{match_id}`\n\n"
                "**MMR, 승패, 기본 경기기록은 건드리지 않습니다.**\n"
                "아래 버튼을 누르면 ROFL에서 추가된 상세스탯만 삭제됩니다."
            ),
            color=0xe67e22,
        )
        embed.add_field(name=f"삭제 대상 {len(rofl_entries)}명", value="\n".join(lines), inline=False)
        view = ReplayDetailCancelConfirmView(
            requester_id=interaction.user.id,
            gid=gid,
            match_id=match_id,
            rank=순번,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    def find_user_champion_detail_entries(guild_data, uid, champion):
        target = normalize_champion_title_key(champion)
        if not target:
            return []
    
        history_by_id = {
            str(record.get("id")): record
            for record in guild_data.get(MATCH_HISTORY_KEY, [])
            if record.get("id")
        }
        found = []
        for match_id, match_entries in match_stats.get_store(guild_data).items():
            entry = (match_entries or {}).get(str(uid))
            if not entry:
                continue
            if normalize_champion_title_key(entry.get("champion")) != target:
                continue
            record = history_by_id.get(str(match_id))
            found.append({
                "match_id": str(match_id),
                "entry": entry,
                "record": record,
                "time": parse_history_time(record) if record else None,
            })
        return sorted(found, key=lambda item: item["time"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    
    def format_detail_delete_candidate(guild, gid, idx, item):
        entry = item["entry"]
        record = item.get("record") or {}
        time_text = record.get("time") or "시간 없음"
        result_text = "승" if entry.get("result") == "win" else "패" if entry.get("result") == "loss" else "결과 없음"
        try:
            awards = match_stats.score_match_awards(bot.user_data.setdefault(gid, {}), item["match_id"])
        except Exception:
            awards = {}
        award_text = ""
        if str((awards.get("mvp") or {}).get("user_id")) == str(entry.get("user_id")):
            award_text = " · MVP"
        elif str((awards.get("ace") or {}).get("user_id")) == str(entry.get("user_id")):
            award_text = " · ACE"
        kills = safe_detail_int(entry.get('kills'))
        deaths = safe_detail_int(entry.get('deaths'))
        assists = safe_detail_int(entry.get('assists'))
        damage = safe_detail_int(entry.get('damage'))
        dpm = safe_detail_float(entry.get('dpm'))
        return (
            f"`{idx}` **{entry.get('champion', '챔피언 없음')}** · {time_text} · `{entry.get('role', '미지정')}` · {result_text}{award_text}\n"
            f"└ KDA **{kills}/{deaths}/{assists}** · "
            f"딜량 **{damage:,}** · 분당 피해량 **{dpm:.0f}** · ID `{item['match_id']}`"
        )
    
    async def delete_champion_detail_data(
        interaction: discord.Interaction,
        유저: discord.Member,
        챔피언: str,
        번호: app_commands.Range[int, 1, 100] = None,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 상세 데이터를 삭제할 수 있습니다.", ephemeral=True)
    
        try:
            gid = str(interaction.guild_id)
            guild_data = bot.user_data.setdefault(gid, {})
            uid = str(유저.id)
            candidates = find_user_champion_detail_entries(guild_data, uid, 챔피언)
            champion_label = str(챔피언 or "").strip()
    
            if not candidates:
                user_champions = sort_champion_summary_rows(match_stats.aggregate_by(guild_data, "champion", user_id=uid))
                sample = ", ".join(str(row.get("label")) for row in user_champions[:10]) if user_champions else "기록 없음"
                return await interaction.response.send_message(
                    f"📭 {유저.mention} 님의 **{champion_label}** 상세 데이터가 없습니다.\n"
                    f"현재 상세스탯 챔피언: {sample}",
                    ephemeral=True
                )
    
            if 번호 is None:
                embed = discord.Embed(
                    title="🧾 삭제할 챔피언 데이터 선택",
                    description=(
                        f"대상: {유저.mention} · 챔피언 **{champion_label}**\n"
                        f"삭제하려면 `/복구관리 작업:상세데이터삭제 유저:@대상 챔피언:{champion_label} 번호:[번호]` 로 다시 입력해주세요."
                    ),
                    color=0xe67e22
                )
                lines = [
                    format_detail_delete_candidate(interaction.guild, gid, idx, item)
                    for idx, item in enumerate(candidates[:20], 1)
                ]
                add_chunked_embed_fields(embed, f"검색 결과 {len(candidates)}건", lines, inline=False)
                if len(candidates) > 20:
                    embed.set_footer(text="상위 20건만 표시했습니다. 번호는 표시된 목록 기준입니다.")
                return await interaction.response.send_message(embed=embed, ephemeral=True)
    
            if 번호 > len(candidates):
                return await interaction.response.send_message(
                    f"⚠️ 삭제 가능한 번호는 1~{len(candidates)}번입니다.",
                    ephemeral=True
                )
    
            target = candidates[번호 - 1]
            detail_store = match_stats.get_store(guild_data)
            match_entries = detail_store.get(target["match_id"], {})
            deleted = match_entries.pop(uid, None)
            if deleted is None:
                return await interaction.response.send_message("⚠️ 이미 삭제되었거나 데이터를 찾을 수 없습니다.", ephemeral=True)
            if not match_entries:
                detail_store.pop(target["match_id"], None)
            bot.save_lucid_data(gid)
    
            embed = discord.Embed(
                title="🗑️ 챔피언 상세 데이터 삭제 완료",
                description=f"대상: {유저.mention} · 번호 **{번호}** · 경기 ID `{target['match_id']}`",
                color=0xe74c3c
            )
            embed.add_field(
                name="삭제된 기록",
                value=format_detail_delete_candidate(interaction.guild, gid, 번호, target),
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as exc:
            logger.exception("데이터삭제 명령 처리 실패")
            if interaction.response.is_done():
                return await interaction.followup.send(f"⚠️ 데이터삭제 처리 중 오류: `{str(exc)[:900]}`", ephemeral=True)
            return await interaction.response.send_message(f"⚠️ 데이터삭제 처리 중 오류: `{str(exc)[:900]}`", ephemeral=True)
    
    @bot.tree.command(name="수상기록", description="상세스탯 기준 MVP/ACE 수상 기록을 확인합니다.")
    async def detail_award_records(
        interaction: discord.Interaction,
        유저: discord.Member = None,
        페이지: app_commands.Range[int, 1, 50] = 1,
    ):
        gid = str(interaction.guild_id)
        guild_data = bot.user_data.setdefault(gid, {})
        if 유저:
            row = match_stats.aggregate_user(guild_data, str(유저.id))
            if not row:
                return await interaction.response.send_message("📭 아직 기록된 상세 스탯이 없습니다.", ephemeral=True)
            embed = discord.Embed(
                title=f"🏅 {유저.display_name} MVP / ACE 수상 기록",
                description=(
                    f"상세 기록 **{row['games']}전**\n"
                    f"MVP **{row.get('mvp_count', 0)}회** | ACE **{row.get('ace_count', 0)}회**\n"
                    f"KDA **{row['kda']:.1f}** | 분당 피해량 **{row['dpm']:.0f}** | 킬 관여율 **{row['avg_kp']:.1f}%**"
                ),
                color=0xf1c40f
            )
            return await interaction.response.send_message(embed=embed)
    
        embed = build_detail_award_ranking_embed(interaction.guild, gid, guild_data, page=페이지)
        await interaction.response.send_message(embed=embed)
    
    def build_detail_award_ranking_embed(guild, gid, guild_data, *, page=1, page_size=10):
        counts = {}
        skipped = 0
        for match_id in list(match_stats.get_store(guild_data).keys()):
            try:
                awards = match_stats.score_match_awards(guild_data, match_id)
            except Exception:
                skipped += 1
                logger.exception("수상랭킹 경기 수상 계산 실패: %s", match_id)
                continue
            for award_key, count_key in (("mvp", "mvp_count"), ("ace", "ace_count")):
                award = awards.get(award_key)
                if not award:
                    continue
                uid = str(award.get("user_id"))
                if (
                    not uid
                    or uid == "None"
                    or (
                        callable(getattr(guild, "get_member", None))
                        and guild.get_member(int(uid)) is None
                    )
                ):
                    continue
                bucket = counts.setdefault(uid, {"mvp_count": 0, "ace_count": 0})
                bucket[count_key] += 1
        rows = []
        for uid, count in counts.items():
            rows.append({
                "uid": uid,
                "mvp_count": count.get("mvp_count", 0),
                "ace_count": count.get("ace_count", 0),
            })
        rows.sort(key=lambda row: (row["mvp_count"] + row["ace_count"], row["mvp_count"], row["ace_count"]), reverse=True)
    
        total_pages = max(1, (len(rows) + page_size - 1) // page_size)
        page = max(1, min(int(page or 1), total_pages))
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
    
        embed = discord.Embed(title="🏅 MVP / ACE 수상 랭킹", color=0xf1c40f)
        if not rows:
            embed.description = "📭 아직 MVP/ACE를 계산할 상세 스탯 기록이 없습니다."
            return embed
    
        lines = []
        for idx, row in enumerate(page_rows, start + 1):
            name = get_member_display_name(guild, gid, row["uid"])
            total = row["mvp_count"] + row["ace_count"]
            rank_icon = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "▫️"
            lines.append(
                f"`#{idx:02d}` {rank_icon} **{name}**\n"
                f"└ 합계 **{total}회** · MVP **{row['mvp_count']}회** · ACE **{row['ace_count']}회**"
            )
        embed.description = "\n\n".join(lines)
        footer = f"{page}/{total_pages}페이지 · 정렬: MVP+ACE 합계 우선, 동률이면 MVP 많은 순"
        if skipped:
            footer += f" · 계산 제외 경기 {skipped}개"
        embed.set_footer(text=footer)
        return embed
    
    async def detail_award_ranking(interaction: discord.Interaction, 페이지: app_commands.Range[int, 1, 50] = 1):
        gid = str(interaction.guild_id)
        guild_data = bot.user_data.setdefault(gid, {})
        try:
            embed = build_detail_award_ranking_embed(interaction.guild, gid, guild_data, page=페이지, page_size=10)
            await interaction.response.send_message(embed=embed)
        except Exception as exc:
            logger.exception("수상랭킹 명령 처리 실패")
            await interaction.response.send_message(f"⚠️ 수상랭킹 처리 중 오류: `{str(exc)[:900]}`", ephemeral=True)
    
    async def champion_detail_stats(
        interaction: discord.Interaction,
        유저: discord.Member = None,
        라인: app_commands.Choice[str] = None,
        페이지: app_commands.Range[int, 1, 50] = 1,
    ):
        try:
            gid = str(interaction.guild_id)
            target_id = str(유저.id) if 유저 else None
            guild_data = bot.user_data.setdefault(gid, {})
            line_value = getattr(라인, "value", 라인) if 라인 else ""
            role = normalize_role_name(line_value)
            if line_value and not role:
                return await interaction.response.send_message(
                    "⚠️ 라인은 `탑`, `정글`, `미드`, `원딜`, `서폿` 중 하나로 입력해주세요.",
                    ephemeral=True
                )
    
            rows = sort_champion_summary_rows(
                aggregate_detail_entries(guild_data, user_id=target_id, role=role, group_key="champion")
            )
            role_label = f" · {role}" if role else ""
            title = f"🧾 {유저.display_name} 챔피언 통계{role_label}" if 유저 else f"🧾 서버 챔피언 통계{role_label}"
            if 유저:
                embed = build_champion_personal_stats_embed(
                    title,
                    rows,
                    "📭 아직 기록된 챔피언 상세 스탯이 없습니다.",
                    include_dpm=True,
                    role=role,
                    page=페이지,
                    page_size=10,
                )
            else:
                embed = build_champion_simple_stats_embed(
                    title,
                    rows,
                    "📭 아직 기록된 챔피언 상세 스탯이 없습니다.",
                    page=페이지,
                    page_size=10,
                )
                if role == "서폿":
                    embed.set_footer(text=f"{페이지}/{max(1, (len(rows) + 9) // 10)}페이지 · 상세스탯 저장 기록 기준 · 서폿 분당 피해량 제외")
            await interaction.response.send_message(embed=embed)
        except Exception as exc:
            logger.exception("챔피언통계 명령 처리 실패")
            message = f"⚠️ 챔피언통계 처리 중 오류: `{str(exc)[:900]}`"
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
    
    async def champion_winrate_stats(
        interaction: discord.Interaction,
        유저: discord.Member = None,
        최소판수: app_commands.Range[int, 1, 50] = 1,
        페이지: app_commands.Range[int, 1, 50] = 1,
    ):
        gid = str(interaction.guild_id)
        target_id = str(유저.id) if 유저 else None
        guild_data = bot.user_data.setdefault(gid, {})
        effective_min_games = 최소판수 if 유저 else max(5, 최소판수)
        rows = [
            row for row in aggregate_detail_entries(guild_data, user_id=target_id, group_key="champion")
            if row.get("games", 0) >= effective_min_games
        ]
        rows = sort_champion_winrate_rows(rows)
    
        page_size = 10
        total_pages = max(1, (len(rows) + page_size - 1) // page_size)
        if 페이지 > total_pages:
            페이지 = total_pages
        page_rows = rows[(페이지 - 1) * page_size:페이지 * page_size]
    
        title = f"🏆 {유저.display_name} 챔피언 승률" if 유저 else "🏆 서버 챔피언 승률"
        embed = discord.Embed(title=title, color=0xf1c40f)
        if not rows:
            embed.description = f"📭 최소 {effective_min_games}판 이상 기록된 챔피언이 없습니다."
            return await interaction.response.send_message(embed=embed)
    
        lines = []
        start_rank = (페이지 - 1) * page_size + 1
        for idx, row in enumerate(page_rows, start_rank):
            if 유저:
                lines.append(format_personal_champion_line(idx, row))
            else:
                lines.append(
                    f"`{idx:>2}` **{row['label']}** · "
                    f"{row['games']}전 {row['wins']}승 {row['losses']}패 · "
                    f"승률 **{row['winrate']:.1f}%**"
                )
        embed.description = "\n\n".join(lines) if 유저 else "\n".join(lines)
        embed.set_footer(text=f"{페이지}/{total_pages}페이지 · 상세스탯 저장 기록 기준 · 최소 {effective_min_games}판 · 승률순 정렬")
        await interaction.response.send_message(embed=embed)
    
    # 상세 조회/복구 작업은 `/수상기록`, `/챔피언통계`, `/챔피언승률`, `/리플레이`, `/복구관리`로 분리됨.
    
    @bot.tree.command(
        name="승패기록테스트",
        description="[내전 관리자] ROFL 승패/상세기록/음성 종료 흐름을 실제 실행 후 기록만 원상복구합니다.",
    )
    @app_commands.describe(
        파일="테스트할 10인 .rofl 파일",
        큐="테스트에 사용할 비어 있는 일반 내전 큐 번호",
    )
    @app_commands.choices(
        큐=[app_commands.Choice(name=f"{i}번 큐", value=str(i)) for i in range(1, 6)]
    )
    async def match_record_full_pipeline_test(
        interaction: discord.Interaction,
        파일: discord.Attachment,
        큐: app_commands.Choice[str],
    ):
        # Discord interactions must be acknowledged within ~3 seconds.
        # Do this before runtime hydration/validation so a busy event loop,
        # startup restore, or API rate-limit cannot expire the interaction.
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except discord.NotFound:
            logger.warning(
                "승패기록테스트 interaction 만료: guild_id=%s user_id=%s",
                getattr(interaction, "guild_id", None),
                getattr(getattr(interaction, "user", None), "id", None),
            )
            return

        _sync_runtime()
        if not is_match_admin(interaction):
            return await interaction.followup.send(
                "🚫 내전 관리자만 사용할 수 있습니다.",
                ephemeral=True,
            )
        if not str(파일.filename or "").lower().endswith(".rofl"):
            return await interaction.followup.send(
                "⚠️ `.rofl` 파일만 사용할 수 있습니다.",
                ephemeral=True,
            )

        gid = str(interaction.guild_id)
        queue_key = int(큐.value)

        if bot.active_games.get(gid, {}).get(queue_key):
            return await interaction.followup.send(
                f"⚠️ {queue_key}번 큐에 실제 진행 중인 경기가 있습니다. 빈 큐를 선택해주세요.",
                ephemeral=True,
            )
        if bot.queues.get(gid, {}).get(queue_key):
            return await interaction.followup.send(
                f"⚠️ {queue_key}번 큐 대기열에 참가자가 있습니다. 완전히 빈 큐에서만 테스트할 수 있습니다.",
                ephemeral=True,
            )

        process_key = (gid, queue_key)
        if process_key in bot.processing_games:
            return await interaction.followup.send(
                "⏳ 해당 큐 결과가 이미 처리 중입니다.",
                ephemeral=True,
            )

        # Snapshot all persisted guild state before touching the real match pipeline.
        # This intentionally includes match history, replay-detail store, titles,
        # rival data, MMR/wins/losses/streaks and any other future guild-data keys.
        guild_existed = gid in bot.user_data
        guild_snapshot = copy.deepcopy(bot.user_data.get(gid, {}))
        active_games_snapshot = copy.deepcopy(bot.active_games.get(gid, {}))
        queues_snapshot = copy.deepcopy(bot.queues.get(gid, {}))
        history_snapshot = copy.deepcopy(bot.history.get(gid, {}))
        title_batch_snapshot = copy.deepcopy(bot.title_batch.get(gid, [])) if bot.title_batch is not None else None

        participant_role_snapshots = {}
        participant_ids = []
        created_test_state = False
        test_completed = False
        rollback_completed = False
        detail_saved_count = 0
        match_id = None
        winner = None
        warnings = []
        stage_lines = []

        bot.processing_games.add(process_key)

        try:
            # 1) Decode the same ROFL detail rows used by the real replay pipeline.
            rofl_rows = await analyze_rofl_detail_file(파일)
            preview_record, game_state, warnings = build_retroactive_rofl_match(
                interaction.guild,
                gid,
                rofl_rows,
            )

            winner = str(preview_record.get("winner") or "")
            if winner not in ("blue", "red"):
                raise ValueError("ROFL 승리팀을 확인하지 못했습니다.")

            participant_ids = list(game_state.get("blue", [])) + list(game_state.get("red", []))
            normalized_ids = {str(uid) for uid in participant_ids}
            if len(normalized_ids) != 10:
                raise ValueError(f"ROFL 참가자 Discord 매칭이 10명이 아닙니다. ({len(normalized_ids)}/10)")

            stage_lines.append("✅ ROFL 참가자 매칭 `10/10`")
            stage_lines.append(
                f"✅ 팀/승리 판정 `블루 5 : 레드 5 · {'블루' if winner == 'blue' else '레드'} 승리`"
            )

            # Remember participant Discord roles. Match/detail processing can sync
            # tier/title roles; restore them after the data snapshot is restored.
            for uid in normalized_ids:
                try:
                    member = interaction.guild.get_member(int(uid))
                except (TypeError, ValueError):
                    member = None
                if member is None:
                    try:
                        member = await interaction.guild.fetch_member(int(uid))
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        member = None
                if member:
                    participant_role_snapshots[uid] = {
                        role.id
                        for role in member.roles
                        if role != interaction.guild.default_role
                    }

            # 2) Reproduce a real active game and real team voice-room creation.
            bot.active_games.setdefault(gid, {})[queue_key] = game_state
            bot.queues.setdefault(gid, {})[queue_key] = []
            created_test_state = True

            get_names = runtime["get_classic_voice_channel_names"]
            create_voice = runtime["create_and_move_team_voice_channels"]
            blue_name, red_name = get_names(queue_key)

            blue_members = [
                interaction.guild.get_member(int(uid))
                for uid in game_state.get("blue", [])
                if str(uid).isdigit()
            ]
            red_members = [
                interaction.guild.get_member(int(uid))
                for uid in game_state.get("red", [])
                if str(uid).isdigit()
            ]

            connected_before = sum(
                1
                for member in blue_members + red_members
                if member and member.voice and member.voice.channel
            )

            created_voice_channels = await create_voice(
                interaction.guild,
                [(blue_name, blue_members), (red_name, red_members)],
                move_members=True,
            )
            created_voice_ids = {
                int(vc.id)
                for vc in (created_voice_channels or [])
                if vc is not None and getattr(vc, "id", None) is not None
            }
            connected_participant_ids = {
                int(member.id)
                for member in blue_members + red_members
                if member and member.voice and member.voice.channel
            }
            stage_lines.append(
                f"✅ 팀 음성방 생성/이동 실행 `현재 접속자 {connected_before}명`"
            )

            # 3) Run the REAL classic-win path. This updates the real in-memory/
            # persistent state and executes the same voice cleanup as production.
            before_count = len(runtime["get_valid_match_history"](gid))
            await runtime["process_classic_win"](
                interaction,
                gid,
                queue_key,
                "블루" if winner == "blue" else "레드",
                False,
                game_state,
                retroactive=False,
            )
            after_count = len(runtime["get_valid_match_history"](gid))
            if after_count <= before_count:
                raise RuntimeError("승패/MMR 경기 기록이 생성되지 않았습니다.")
            stage_lines.append("✅ 실제 승패/MMR/연승/경기기록 처리")

            # Verify the physical Discord side, not just that cleanup was called.
            waiting_vc = discord.utils.get(interaction.guild.voice_channels, name="내전 대기실")
            moved_to_waiting_ids = set()
            if waiting_vc is not None:
                moved_to_waiting_ids = {
                    int(member.id)
                    for member in list(waiting_vc.members)
                    if int(member.id) in connected_participant_ids
                }

            moved_expected = len(connected_participant_ids)
            moved_actual = len(moved_to_waiting_ids)

            surviving_team_channels = [
                interaction.guild.get_channel(channel_id)
                for channel_id in created_voice_ids
            ]
            surviving_team_channels = [
                channel for channel in surviving_team_channels
                if channel is not None
            ]
            deleted_actual = len(created_voice_ids) - len(surviving_team_channels)
            deleted_expected = len(created_voice_ids)

            if moved_expected > 0 and moved_actual != moved_expected:
                raise RuntimeError(
                    f"대기실 실제 이동 검증 실패: {moved_actual}/{moved_expected}명"
                )
            if deleted_expected > 0 and deleted_actual != deleted_expected:
                remaining_names = ", ".join(
                    getattr(channel, "name", str(getattr(channel, "id", "?")))
                    for channel in surviving_team_channels
                )
                raise RuntimeError(
                    f"팀 음성방 삭제 검증 실패: {deleted_actual}/{deleted_expected}개"
                    + (f" · 남은 방: {remaining_names}" if remaining_names else "")
                )

            stage_lines.append(
                f"✅ 대기실 실제 이동 `{moved_actual}/{moved_expected}명`"
            )
            stage_lines.append(
                f"✅ 팀 음성방 실제 삭제 `{deleted_actual}/{deleted_expected}개`"
            )

            # 4) Save detail exactly through the production ROFL detail path.
            detail = await save_rofl_detail_for_latest_record(
                interaction,
                gid,
                queue_key,
                rofl_rows,
            )
            match_id = detail.get("match_id")
            detail_saved_count = int(detail.get("saved_count", 0) or 0)
            if detail_saved_count != 10:
                raise RuntimeError(
                    f"ROFL 상세전적이 10/10 저장되지 않았습니다. ({detail_saved_count}/10)"
                )
            stage_lines.append(f"✅ ROFL 상세전적 저장 `{detail_saved_count}/10`")
            stage_lines.append("✅ 상세전적 후속 계산/수상 처리 실행")
            test_completed = True

        except Exception as exc:
            logger.exception(
                "ROFL 롤백 테스트 실행 실패: guild_id=%s queue=%s user_id=%s",
                interaction.guild_id,
                queue_key,
                interaction.user.id,
            )
            stage_lines.append(f"❌ 테스트 단계 오류 `{str(exc)[:500]}`")

        finally:
            # 5) Restore every persisted/in-memory data structure. Voice movement
            # and channel deletion intentionally remain because those are the
            # physical behaviours this command is meant to verify.
            try:
                if guild_existed:
                    bot.user_data[gid] = copy.deepcopy(guild_snapshot)
                else:
                    bot.user_data.pop(gid, None)

                if active_games_snapshot:
                    bot.active_games[gid] = copy.deepcopy(active_games_snapshot)
                else:
                    bot.active_games.pop(gid, None)

                if queues_snapshot:
                    bot.queues[gid] = copy.deepcopy(queues_snapshot)
                else:
                    bot.queues.pop(gid, None)

                if history_snapshot:
                    bot.history[gid] = copy.deepcopy(history_snapshot)
                else:
                    bot.history.pop(gid, None)

                if bot.title_batch is not None:
                    if title_batch_snapshot is None:
                        bot.title_batch.pop(gid, None)
                    else:
                        bot.title_batch[gid] = copy.deepcopy(title_batch_snapshot)

                # Persist the restored snapshot so DB/disk state matches memory.
                bot.save_lucid_data(gid)

                # Restore Discord roles for replay participants. Only roles that the
                # bot can manage are changed; managed/integration roles are ignored.
                restored_role_members = 0
                for uid, original_role_ids in participant_role_snapshots.items():
                    try:
                        member = interaction.guild.get_member(int(uid))
                    except (TypeError, ValueError):
                        member = None
                    if member is None:
                        continue

                    current_editable = {
                        role.id: role
                        for role in member.roles
                        if role != interaction.guild.default_role
                        and not role.managed
                        and role < interaction.guild.me.top_role
                    }
                    original_editable_ids = {
                        role_id
                        for role_id in original_role_ids
                        if (
                            (role := interaction.guild.get_role(int(role_id))) is not None
                            and not role.managed
                            and role < interaction.guild.me.top_role
                        )
                    }

                    to_remove = [
                        role
                        for role_id, role in current_editable.items()
                        if role_id not in original_editable_ids
                    ]
                    to_add = [
                        interaction.guild.get_role(int(role_id))
                        for role_id in original_editable_ids
                        if role_id not in current_editable
                    ]
                    to_add = [role for role in to_add if role is not None]

                    try:
                        if to_remove:
                            await member.remove_roles(
                                *to_remove,
                                reason="ROFL 파이프라인 테스트 롤백",
                            )
                        if to_add:
                            await member.add_roles(
                                *to_add,
                                reason="ROFL 파이프라인 테스트 롤백",
                            )
                        restored_role_members += 1
                    except (discord.Forbidden, discord.HTTPException) as role_exc:
                        logger.warning(
                            "ROFL 테스트 역할 롤백 일부 실패: guild_id=%s user_id=%s error=%s",
                            interaction.guild_id,
                            uid,
                            role_exc,
                        )

                rollback_completed = True
                stage_lines.append(
                    f"✅ 테스트 기록 롤백 완료 `MMR/전적/상세전적/서버데이터 복구 · 역할 {restored_role_members}명 확인`"
                )
            except Exception as rollback_exc:
                logger.exception(
                    "ROFL 테스트 롤백 실패: guild_id=%s queue=%s",
                    interaction.guild_id,
                    queue_key,
                )
                stage_lines.append(
                    f"🚨 **롤백 실패** `{str(rollback_exc)[:500]}`"
                )
            finally:
                bot.processing_games.discard(process_key)

        color = 0x2ECC71 if test_completed and rollback_completed else 0xE74C3C
        title = (
            "🧪 ROFL 실전 파이프라인 테스트 완료"
            if test_completed and rollback_completed
            else "🧪 ROFL 실전 파이프라인 테스트 확인 필요"
        )

        embed = discord.Embed(
            title=title,
            description="\n".join(stage_lines),
            color=color,
        )
        if match_id:
            embed.add_field(
                name="테스트 중 생성된 경기 ID",
                value=f"`{match_id}` · 롤백 후 삭제됨",
                inline=False,
            )
        if warnings:
            embed.add_field(
                name="매칭 참고",
                value="\n".join(warnings[:5]),
                inline=False,
            )

        if rollback_completed:
            embed.set_footer(
                text="음성 이동/팀방 삭제만 실제로 유지되며 테스트 경기 기록은 원상복구됩니다."
            )
        else:
            embed.set_footer(
                text="롤백 실패가 표시되면 추가 테스트를 중단하고 로그를 확인해주세요."
            )

        await interaction.followup.send(embed=embed, ephemeral=True)



    @bot.tree.command(name="리플레이기록", description="[내전 관리자] ROFL 리플레이 파일을 바로 업로드해 상세 기록을 저장합니다.")
    @app_commands.describe(
        파일="업로드할 .rofl 리플레이 파일",
        순번="자동 매칭이 애매할 때 최근 몇 번째 경기인지 직접 지정합니다.",
    )
    async def replay_record_direct(
        interaction: discord.Interaction,
        파일: discord.Attachment,
        순번: app_commands.Range[int, 1, 500] = None,
    ):
        return await detail_stat_rofl_analyze(interaction, 파일, 순번=순번, 최근경기수=200)
    
    
    @bot.tree.command(name="리플레이기록취소", description="[내전 관리자] 경기 순번을 골라 해당 경기의 상세기록을 취소합니다.")
    @app_commands.describe(순번="/경기기록 기준 최근 몇 번째 경기의 리플레이 상세기록을 취소할지 선택합니다.")
    async def replay_record_undo_direct(
        interaction: discord.Interaction,
        순번: app_commands.Range[int, 1, 50],
    ):
        return await detail_stat_record_cancel(interaction, 순번=순번)
    
    
    @bot.tree.command(name="리플레이누락확인", description="[내전 관리자] 리플레이 기록이 누락된 경기를 확인합니다.")
    @app_commands.describe(
        최근경기수="확인할 최근 경기 수입니다.",
        기준날짜="이 날짜 이후 경기만 확인합니다. 예: 2026-06-25, 6/25, 0625",
    )
    async def replay_missing_check_direct(
        interaction: discord.Interaction,
        최근경기수: app_commands.Range[int, 1, 100] = 30,
        기준날짜: str = "",
    ):
        return await detail_stat_missing_check(interaction, 최근경기수=최근경기수, 기준날짜=기준날짜)
    
    async def user_champion_winrate_stats(
        interaction: discord.Interaction,
        유저: discord.Member,
        최소판수: app_commands.Range[int, 1, 50] = 1,
    ):
        gid = str(interaction.guild_id)
        guild_data = bot.user_data.setdefault(gid, {})
        rows = [
            row for row in aggregate_detail_entries(guild_data, user_id=str(유저.id), group_key="champion")
            if row.get("games", 0) >= 최소판수
        ]
        rows = sort_champion_winrate_rows(rows)
    
        embed = discord.Embed(title=f"🏆 {유저.display_name} 챔피언별 승률", color=0xf1c40f)
        if not rows:
            embed.description = f"📭 최소 {최소판수}판 이상 기록된 챔피언이 없습니다."
            return await interaction.response.send_message(embed=embed)
    
        lines = []
        for idx, row in enumerate(rows[:15], 1):
            lines.append(format_personal_champion_line(idx, row))
        embed.description = "\n\n".join(lines)
        embed.set_footer(text=f"상세스탯 저장 기록 기준 · 최소 {최소판수}판 · 승률순 정렬")
        await interaction.response.send_message(embed=embed)
    
    async def role_detail_stats(interaction: discord.Interaction, 유저: discord.Member = None):
        gid = str(interaction.guild_id)
        target_id = str(유저.id) if 유저 else None
        guild_data = bot.user_data.setdefault(gid, {})
        rows = match_stats.sort_rows(match_stats.aggregate_by(guild_data, "role", user_id=target_id), key="games")
        title = f"🧭 {유저.display_name} 라인 상세 통계" if 유저 else "🧭 서버 라인 상세 통계"
        embed = discord.Embed(title=title, color=0x3498db)
        if not rows:
            embed.description = "📭 아직 기록된 라인 상세 스탯이 없습니다."
            return await interaction.response.send_message(embed=embed)
    
        lines = []
        for row in rows[:15]:
            metric_text = (
                f"KDA **{row['kda']:.1f}** · 킬 관여율 **{row['avg_kp']:.1f}%**"
                if row.get("label") == "서폿"
                else f"KDA **{row['kda']:.1f}** · 분당 피해량 **{row['dpm']:.0f}** · 킬 관여율 **{row['avg_kp']:.1f}%**"
            )
            lines.append(
                f"**{row['label']}** · {row['games']}전 {row['wins']}승 {row['losses']}패 "
                f"({row['winrate']:.1f}%)\n"
                f"{metric_text}"
            )
        embed.description = "\n".join(lines)
        embed.set_footer(text="라인별 상세스탯 저장 기록 기준")
        await interaction.response.send_message(embed=embed)
    
    async def send_period_summary(interaction: discord.Interaction, title: str, start_time: datetime):
        gid = str(interaction.guild_id)
        summary = summarize_match_period(gid, start_time, guild=interaction.guild)
        point_delta = summary['point_delta']
        gains = {uid: delta for uid, delta in point_delta.items() if delta > 0}
        drops = {uid: delta for uid, delta in point_delta.items() if delta < 0}
    
        embed = discord.Embed(
            title=title,
            description=(
                f"총 **{summary['total']}경기** 진행\n"
                f"공식 내전 **{summary['classic']}경기** · 노밴 **{summary['noban']}경기** · 이벤트 모드 **{summary['event']}경기**"
            ),
            color=0x1abc9c
        )
        embed.add_field(
            name="📈 점수 최다 상승",
            value=format_top_counter(gains, interaction.guild, gid, "MMR 변동 기록 없음"),
            inline=False
        )
        embed.add_field(
            name="📉 점수 최다 하락",
            value=format_top_counter(drops, interaction.guild, gid, "MMR 변동 기록 없음", reverse=False),
            inline=False
        )
        embed.add_field(
            name="🎮 최다 참여",
            value=format_top_participants(summary['participation'], interaction.guild, gid),
            inline=False
        )
        await interaction.response.send_message(embed=embed)


    MVP_POINT_VALUE = 100
    ACE_POINT_VALUE = 50
    
    def get_award_point_rows(gid, start_time=None, end_time=None, guild=None):
        guild_data = bot.user_data.setdefault(str(gid), {})
        points = defaultdict(int)
        mvp_counts = defaultdict(int)
        ace_counts = defaultdict(int)
        for record in get_valid_match_history(str(gid)):
            record_time = parse_history_time(record)
            if start_time and (not record_time or record_time < start_time):
                continue
            if end_time and (not record_time or record_time >= end_time):
                continue
            match_id = record.get("id")
            if not match_id:
                continue
            try:
                awards = match_stats.score_match_awards(guild_data, match_id)
            except Exception:
                continue
            mvp = awards.get("mvp") or {}
            ace = awards.get("ace") or {}
            if mvp.get("user_id"):
                uid = str(mvp["user_id"])
                if not callable(getattr(guild, "get_member", None)) or guild.get_member(int(uid)) is not None:
                    points[uid] += MVP_POINT_VALUE
                    mvp_counts[uid] += 1
            if ace.get("user_id"):
                uid = str(ace["user_id"])
                if not callable(getattr(guild, "get_member", None)) or guild.get_member(int(uid)) is not None:
                    points[uid] += ACE_POINT_VALUE
                    ace_counts[uid] += 1
        rows = [(uid, score, mvp_counts[uid], ace_counts[uid]) for uid, score in points.items()]
        rows.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)
        return rows
    
    def format_award_point_ranking(guild, gid, start_time=None, limit=5):
        rows = get_award_point_rows(gid, start_time=start_time, guild=guild)[:limit]
        if not rows:
            return "아직 MVP/ACE 포인트 기록이 없습니다."
        return "\n".join(
            f"**{idx}위** `{discord.utils.escape_markdown(str(get_registered_display_name(guild, gid, uid)))}` · **{points}P** · MVP {mvp} / ACE {ace}"
            for idx, (uid, points, mvp, ace) in enumerate(rows, 1)
        )
    
    report_period_choices = [
        app_commands.Choice(name="오늘", value="today"),
        app_commands.Choice(name="주간", value="week"),
        app_commands.Choice(name="월간", value="month"),
    ]
    
    @bot.tree.command(name="내전리포트", description="오늘/주간/월간 내전 요약과 MVP 포인트 랭킹을 확인합니다.")
    @app_commands.choices(기간=report_period_choices)
    async def match_report(interaction: discord.Interaction, 기간: app_commands.Choice[str]):
        now = now_kst()
        if 기간.value == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            title = "📅 오늘 내전 리포트"
        elif 기간.value == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            title = "🗓️ 이번 달 내전 리포트"
        else:
            start = now - timedelta(days=7)
            title = "🗓️ 최근 7일 내전 리포트"
        gid = str(interaction.guild_id)
        summary = summarize_match_period(gid, start, guild=interaction.guild)
        gains = {uid: delta for uid, delta in summary['point_delta'].items() if delta > 0}
        drops = {uid: delta for uid, delta in summary['point_delta'].items() if delta < 0}
        embed = discord.Embed(
            title=title,
            description=f"총 **{summary['total']}경기** · 공식 **{summary['classic']}** · 노밴 **{summary['noban']}** · 이벤트 **{summary['event']}**",
            color=0x1abc9c,
        )
        embed.add_field(name="📈 MMR 최다 상승", value=format_top_counter(gains, interaction.guild, gid, "MMR 변동 기록 없음"), inline=False)
        embed.add_field(name="📉 MMR 최다 하락", value=format_top_counter(drops, interaction.guild, gid, "MMR 변동 기록 없음", reverse=False), inline=False)
        embed.add_field(name="🎮 최다 참여", value=format_top_participants(summary['participation'], interaction.guild, gid), inline=False)
        embed.add_field(name="🏆 MVP 포인트 TOP 5", value=format_award_point_ranking(interaction.guild, gid, start), inline=False)
        await interaction.response.send_message(embed=embed)
    
    def format_stats_champion_marker(guild, gid, champion_name):
        """Use only the champion portrait emoji when the server has one; otherwise use the name."""
        name = str(champion_name or "미지정").strip()
        marker = get_champion_display_marker(name, guild, gid)
        if marker != name and marker.startswith("<"):
            return marker.split(" ", 1)[0]
        return name
    
    
    def format_unified_champion_stats_line(guild, gid, idx, row):
        champion = format_stats_champion_marker(guild, gid, row.get("label"))
        return (
            f"`{idx:>2}` {champion} · **{int(row.get('games', 0) or 0)}게임** · "
            f"승률 **{float(row.get('winrate', 0) or 0):.1f}%** · "
            f"KDA **{float(row.get('kda', 0) or 0):.1f}**"
        )
    
    
    class ChampionStatsView(discord.ui.View):
        def __init__(self, guild, gid, target, role, min_games, page, mode="winrate"):
            super().__init__(timeout=900)
            self.mode = mode
            self.guild = guild
            self.gid = gid
            self.target = target
            self.role = role
            self.min_games = min_games
            self.page = page
    
        def make_embed(self, mode):
            target_id = str(self.target.id) if self.target else None
            rows = aggregate_detail_entries(
                bot.user_data.setdefault(self.gid, {}),
                user_id=target_id,
                role=self.role,
                group_key="champion",
            )
    
            if mode == "games":
                rows = sort_champion_summary_rows(rows)
                title = (
                    f"🧾 {self.target.display_name} 챔피언 판수"
                    if self.target else "🧾 서버 챔피언 판수"
                )
                mode_label = "판수순"
            else:
                # 승률 탭은 기존 최소판수 규칙 유지.
                effective = self.min_games if self.target else max(5, self.min_games)
                rows = [r for r in rows if r.get("games", 0) >= effective]
                rows = sort_champion_winrate_rows(rows)
                title = (
                    f"🏆 {self.target.display_name} 챔피언 승률"
                    if self.target else "🏆 서버 챔피언 승률"
                )
                mode_label = "승률순"
    
            page_size = 10
            total_pages = max(1, (len(rows) + page_size - 1) // page_size)
            page = min(self.page, total_pages)
            page_rows = rows[(page - 1) * page_size:page * page_size]
    
            embed = discord.Embed(
                title=title,
                color=0xf1c40f if mode == "winrate" else 0x3498db,
            )
            if not rows:
                embed.description = "📭 조건에 맞는 챔피언 기록이 없습니다."
                return embed
    
            lines = [
                format_unified_champion_stats_line(self.guild, self.gid, idx, row)
                for idx, row in enumerate(page_rows, (page - 1) * page_size + 1)
            ]
            embed.description = "\n\n".join(lines)
            embed.set_footer(text=f"{page}/{total_pages}페이지")
            return embed
    
        def _fresh_view(self, mode):
            view = ChampionStatsView(
                self.guild,
                self.gid,
                self.target,
                self.role,
                self.min_games,
                self.page,
                mode=mode,
            )
            for child in view.children:
                if isinstance(child, discord.ui.Button):
                    if child.label == "승률":
                        child.style = discord.ButtonStyle.primary if mode == "winrate" else discord.ButtonStyle.secondary
                    elif child.label == "판수":
                        child.style = discord.ButtonStyle.primary if mode == "games" else discord.ButtonStyle.secondary
            return view
    
        @discord.ui.button(label="승률", style=discord.ButtonStyle.primary)
        async def winrate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer()
            view = self._fresh_view("winrate")
            await interaction.edit_original_response(embed=view.make_embed("winrate"), view=view)
    
        @discord.ui.button(label="판수", style=discord.ButtonStyle.secondary)
        async def games_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer()
            view = self._fresh_view("games")
            await interaction.edit_original_response(embed=view.make_embed("games"), view=view)
    
    
    @bot.tree.command(name="통계", description="챔피언 통계를 승률/판수 탭으로 확인합니다.")
    @app_commands.choices(라인=[app_commands.Choice(name=r, value=r) for r in ROLES])
    async def unified_stats(
        interaction: discord.Interaction,
        유저: discord.Member = None,
        라인: app_commands.Choice[str] = None,
        최소판수: app_commands.Range[int, 1, 50] = 1,
        페이지: app_commands.Range[int, 1, 50] = 1,
    ):
        await interaction.response.defer()
        role = normalize_role_name(라인.value) if 라인 else None
        view = ChampionStatsView(
            interaction.guild,
            str(interaction.guild_id),
            유저,
            role,
            최소판수,
            페이지,
        )
        await interaction.followup.send(embed=view.make_embed("winrate"), view=view)


    exported = locals().copy()
    exported.pop("runtime", None)
    exported.update({
        "MatchAnalysisContext": MatchAnalysisContext,
        "load_match_analysis_context": load_match_analysis_context,
        "make_match_analysis_context": make_match_analysis_context,
        "resolve_analysis_matchup": resolve_analysis_matchup,
        "build_top_analysis_pages": build_top_analysis_pages,
        "build_jungle_analysis_pages": build_jungle_analysis_pages,
        "build_mid_analysis_pages": build_mid_analysis_pages,
        "build_adc_analysis_pages": build_adc_analysis_pages,
        "build_support_analysis_pages": build_support_analysis_pages,
        "send_match_analysis_pages": send_match_analysis_pages,
        "run_match_analysis_role_smoke_tests": run_match_analysis_role_smoke_tests,
    })
    required_runtime_callables = (
        "apply_ai_mmr_adjustments_for_record",
        "analyze_rofl_detail_file",
        "resolve_rofl_record",
        "get_rofl_record_match_candidates",
        "build_retroactive_rofl_match",
        "get_rofl_champion_map",
        "get_classic_voice_channel_names",
        "create_and_move_team_voice_channels",
        "get_valid_match_history",
        "process_classic_win",
        "build_series_match_history_record",
    )
    available_runtime = dict(runtime)
    available_runtime.update(exported)
    require_runtime_callables(available_runtime, required_runtime_callables)
    return exported
