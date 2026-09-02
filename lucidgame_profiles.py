"""Summoner profiles, rankings, rival records, and title operations."""

import discord
from discord import app_commands
from discord.ext import tasks
import lucidgame_benchmark as benchmark


def configure(runtime):
    globals().update(runtime)


def register_profiles(runtime):
    """Register profile commands and return callbacks used by match orchestration."""
    globals().update(runtime)

    MANUAL_TITLE_DEFS = {
        "💎 서버 서포터즈": "서버 부스트를 통해 커뮤니티 운영과 발전에 도움을 주신 분께 감사의 의미로 지급되는 칭호",
        "🏗️ 개척자": "서버 내전 시스템 초기 세팅에 참여한 관리자에게 수동 지급",
        "📜 기록관": "리플레이 기록/관리 업무에 꾸준히 기여한 관리자에게 수동 지급",
    }
    QUEUE_LINEUP_TITLE_KEYS = (
        "queue_start_5",
        "queue_start_15",
        "queue_final_5",
        "queue_final_15",
    )
    QUEUE_LINEUP_TITLES = tuple(GENERAL_TITLE_DEFS[key] for key in QUEUE_LINEUP_TITLE_KEYS)
    ROLE_MASTER_TITLES = {
        "탑": "🗡️ 탑의 군주",
        "정글": "🧠 협곡의 설계자",
        "미드": "✨ 중앙의 지배자",
        "원딜": "🎯 전장의 사수",
        "서폿": "🛡️ 빛나는 수호자",
    }
    TITLE_SOURCE_NOTES = {
        "🌌 내가 하늘에 서겠다": "〈블리치〉 - 아이젠 소스케",
        "👑 괜찮아, 난 최강이니까": "〈주술회전〉 - 고죠 사토루",
        "👑 너무 강한 말은 쓰지 마": "〈블리치〉 - 아이젠 소스케",
        "계획대로": "〈데스노트〉 - 아이젠 소스케",
        "🧍 도망치면안돼": "〈에반게리온〉 - 이카리 신지",
        "🔥 포기하면 그순간이 시합 종료": "〈슬램덩크〉",
        "🚩 심장을바쳐라": "〈진격의거인〉",
        "🕯️ 사람이 언제 죽는다 생각하나": "〈원피스〉 - Dr. 히루루크",
    }
    FIRST_ROLE_CHALLENGER_TITLE_KEYS = {
        "탑": "first_top_challenger",
        "정글": "first_jungle_challenger",
        "미드": "first_mid_challenger",
        "원딜": "first_adc_challenger",
        "서폿": "first_support_challenger",
    }
    def get_title_system(gid):
        guild_data = bot.user_data.setdefault(gid, {})
        system = guild_data.setdefault(TITLE_SYSTEM_KEY, {})
        system.setdefault("opened", False)
        system.setdefault("opened_by", None)
        system.setdefault("opened_at", None)
        system.setdefault("channel_id", None)
        system.setdefault("first_claims", {})
        system.setdefault("custom_conditions", {})
        seasons = system.setdefault("seasons", {})
        if not system.get("_season_v2_migrated"):
            s1 = seasons.setdefault(TITLE_LEGACY_SEASON, {})
            s1.setdefault("first_claims", dict(system.get("first_claims", {})))
            system["_season_v2_migrated"] = True
        for season_key in (TITLE_LEGACY_SEASON, TITLE_CURRENT_SEASON):
            seasons.setdefault(season_key, {}).setdefault("first_claims", {})
        return system
    def get_title_season_bucket(user_info, season=TITLE_CURRENT_SEASON):
        user_info = ensure_user_format(user_info)
        seasons = user_info["titles"].setdefault("seasons", {})
        bucket = seasons.setdefault(str(season), {})
        bucket.setdefault("owned", [])
        bucket.setdefault("achieved_custom", [])
        return bucket
    def get_title_season_claims(gid, season=TITLE_CURRENT_SEASON):
        system = get_title_system(gid)
        return system.setdefault("seasons", {}).setdefault(str(season), {}).setdefault("first_claims", {})
    def get_title_season_owned(user_info, season):
        return list(get_title_season_bucket(user_info, season).get("owned", []))
    def get_equipped_title(user_info):
        user_info = ensure_user_format(user_info)
        equipped = user_info.get("titles", {}).get("equipped")
        return equipped if equipped else None
    def get_title_unlock_condition(gid, title):
        custom_condition = get_title_system(gid).get("custom_conditions", {}).get(str(title))
        if custom_condition:
            return custom_condition

        champion_condition = get_champion_mastery_title_condition(title)
        if champion_condition:
            return champion_condition

        for info in FIRST_TITLE_DEFS.values():
            if info.get("title") == title:
                return info.get("condition")

        thresholds = get_title_thresholds(gid)
        general_conditions = dict(GENERAL_TITLE_CONDITIONS)
        general_conditions.update({
            "streak_15": f"일반 내전 {thresholds['streak_15']}연승 달성",
            "streak_20": f"일반 내전 {thresholds['streak_20']}연승 달성",
            "league_wins_3": f"{LEAGUE_TITLE_NAME} 우승 {thresholds['league_wins_3']}회 달성",
            "league_wins_5": f"{LEAGUE_TITLE_NAME} 우승 {thresholds['league_wins_5']}회 달성",
            "league_runner_ups_3": f"{LEAGUE_TITLE_NAME} 준우승 {thresholds['league_runner_ups_3']}회 달성",
            "league_finals_5": f"{LEAGUE_TITLE_NAME} 결승 진출 {thresholds['league_finals_5']}회 달성",
            "arena_wins_3": f"아레나 우승 {thresholds['arena_wins_3']}회 달성",
            "arena_wins_5": f"아레나 우승 {thresholds['arena_wins_5']}회 달성",
            "arena_wins_10": f"아레나 우승 {thresholds['arena_wins_10']}회 달성",
            "aram_games_15": f"칼바람 나락 {thresholds['aram_15_games']}판 참가",
            "aram_wins_10": f"칼바람 나락 {thresholds['aram_10_wins']}승 달성",
            "aram_games_30": f"칼바람 나락 {thresholds['aram_30_games']}판 참가",
            "aram_wins_20": f"칼바람 나락 {thresholds['aram_20_wins']}승 달성",
            "aram_high_winrate": f"칼바람 나락 {thresholds['aram_15_games']}판 이상 + 승률 70% 이상",
            "event_all_round_player": f"{LEAGUE_TITLE_NAME}/아레나 우승 경험 + 칼바람 나락 {thresholds['event_all_round_aram_wins']}승",
            "event_wins_20": f"이벤트 모드 통합 {thresholds['event_wins_20']}승 달성",
            "event_wins_30": f"이벤트 모드 통합 {thresholds['event_wins_30']}승 달성",
            "event_wins_50": f"이벤트 모드 통합 {thresholds['event_wins_50']}승 달성",
            "all_roles_20": f"모든 라인 {thresholds['all_roles_20']}판 이상 달성",
            "all_roles_50": f"모든 라인 {thresholds['all_roles_50']}판 이상 달성",
            "all_roles_20_master": f"모든 라인 {thresholds['all_roles_20']}판 이상 + 종합 평균 MMR {TITLE_MMR_ALL_ROLES_SKILLED}점 이상",
            "cost_effective_model": f"라인 MMR {TITLE_MMR_COST_EFFECTIVE_GAP}점 이상 열세 경기 {thresholds['lane_deficit_wins']}승 달성",
            "underdog_hunter": f"라인 MMR {TITLE_MMR_UNDERDOG_GAP}점 이상 열세 경기 {thresholds['lane_deficit_200_wins']}승 달성",
            "disadvantage_taste": f"팀 평균 MMR {TITLE_MMR_TEAM_DEFICIT_GAP}점 이상 열세 경기 {thresholds['team_deficit_150_wins']}승 달성",
            "score_is_extra": f"라인 MMR {TITLE_MMR_SCORE_IS_EXTRA_GAP}점 이상 열세 경기 {thresholds['lane_deficit_games_wr']}판 이상 + 승률 60% 이상",
            "peak_confiscator": f"라인 MMR {TITLE_MMR_PEAK_GAP}점 이상 열세 경기 {thresholds['lane_deficit_300_wins']}승 달성",
        })
        for key, owned_title in GENERAL_TITLE_DEFS.items():
            if owned_title == title:
                return general_conditions.get(key)

        for role, owned_title in ROLE_MASTER_TITLES.items():
            if owned_title == title:
                return f"{role} {thresholds['role_master_games']}판 이상 + 해당 라인 승률 60% 이상"

        if title in MANUAL_TITLE_DEFS:
            return MANUAL_TITLE_DEFS[title]

        return None
    def get_title_source_note(title):
        return TITLE_SOURCE_NOTES.get(str(title or "").strip())
    def format_title_condition_block(gid, title, condition=None):
        condition = condition or get_title_unlock_condition(gid, title)
        if not condition:
            return ""
        lines = ["달성 조건"]
        lines.append(condition)
        return "\n" + "\n".join(lines) + "\n\n"
    def format_title_condition_summary(gid, title, condition=None):
        condition = condition or get_title_unlock_condition(gid, title)
        lines = []
        if condition:
            lines.append(f"  └ {condition}")
        return "\n".join(lines)
    def format_title_source_note_line(title):
        source_note = get_title_source_note(title)
        if source_note:
            return f"\n_{source_note}_"
        return ""
    def get_custom_title_unlock_condition(gid, kind, display_name):
        thresholds = get_title_thresholds(gid)
        if kind == "dynasty":
            return f"{LEAGUE_TITLE_NAME} 3회 연속 우승 달성"
        if kind == "event_legend":
            return f"이벤트 모드 통합 {thresholds['event_legend_wins']}승 서버 최초 달성"
        if kind == "first_low_tier_3_streak":
            return "저티어 큐 3연승 서버 최초 달성"
        if str(kind).startswith("duo:"):
            return f"{display_name} 기준 달성"
        return None
    def format_lineup_title_badge(user_info):
        title = get_equipped_title(user_info)
        if not title:
            return ""
        return str(title).strip()
    def title_has_embedded_name(title):
        title_text = str(title)
        return (
            title_text.endswith("의 왕조")
            or title_text.startswith("🌟 전설의 ")
            or title_text.startswith("🌟 라이징 스타 ")
        )
    def format_profile_equipped_title(title):
        title_text = str(title or "").strip()
        if title_text.startswith("🤝 ") and "님과의 환상 콤비" in title_text:
            partner = title_text[2:].split("님과의 환상 콤비", 1)[0].strip()
            compact_partner = compact_riot_name(partner)
            if compact_partner:
                return f"🤝 {compact_partner}님과의 환상 콤비"
        return title_text
    def format_user_equipped_title(guild, gid, user_info, title):
        title_text = str(title or "").strip()
        if title_text.startswith("🤝 ") and "님과의 환상 콤비" in title_text:
            duo_kinds = [
                str(kind) for kind in user_info.get("titles", {}).get("achieved_custom", [])
                if str(kind).startswith("duo:")
            ]
            if len(duo_kinds) == 1:
                partner_uid = duo_kinds[0].split(":", 1)[1]
                partner_name = compact_riot_name(get_member_display_name(guild, gid, partner_uid))
                if partner_name:
                    return f"🤝 {partner_name}님과의 환상 콤비"
        return format_title_display(guild, gid, format_profile_equipped_title(title_text))
    def format_profile_title(lol_name, suffix, equipped_title=None, default_icon="👤"):
        if equipped_title:
            if title_has_embedded_name(equipped_title):
                return f"{equipped_title}님의 {suffix}"
            return f"{equipped_title}[{lol_name}]님의 {suffix}"
        return f"{default_icon} {lol_name} 님의 {suffix}"
    def add_title_to_user(gid, uid, title, season=TITLE_CURRENT_SEASON):
        user_data = bot.user_data.setdefault(gid, {}).setdefault(str(uid), make_default_user(f"UID {uid}"))
        user_info = ensure_user_format(user_data)
        season_owned = get_title_season_bucket(user_info, season).setdefault("owned", [])
        if title in season_owned:
            return False
        season_owned.append(title)
        # 기존 UI/장착 호환을 위해 owned는 시즌 전체의 합집합으로 유지한다.
        owned = user_info["titles"].setdefault("owned", [])
        if title not in owned:
            owned.append(title)
        return True
    def clear_queue_lineup_titles(user_info, reset_counts=True):
        user_info = ensure_user_format(user_info)
        titles = user_info["titles"]
        owned = titles.setdefault("owned", [])
        removed = [title for title in QUEUE_LINEUP_TITLES if title in owned]
        if removed:
            titles["owned"] = [title for title in owned if title not in QUEUE_LINEUP_TITLES]
            for bucket in titles.get("seasons", {}).values():
                if isinstance(bucket, dict):
                    bucket["owned"] = [title for title in bucket.get("owned", []) if title not in QUEUE_LINEUP_TITLES]
            if titles.get("equipped") in QUEUE_LINEUP_TITLES:
                titles["equipped"] = None

        if reset_counts:
            stats = user_info.setdefault("queue_title_stats", {})
            stats["start_count"] = 0
            stats["final_count"] = 0

        return removed
    def mark_first_title_claimed(gid, key, uid, title, season=TITLE_CURRENT_SEASON):
        claims = get_title_season_claims(gid, season)
        if key in claims:
            return False
        claims[key] = {
            "user_id": str(uid),
            "title": title,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            "season": str(season),
        }
        return True
    async def get_title_notice_channel(interaction, gid):
        channel_id = get_title_system(gid).get("channel_id")
        guild = getattr(interaction, "guild", None)
        if channel_id:
            try:
                channel = guild.get_channel(int(channel_id)) if guild else None
                if channel:
                    return channel
            except (TypeError, ValueError):
                pass
        channel = getattr(interaction, "channel", None)
        if channel:
            return channel
        return await get_match_output_channel(guild, gid)
    async def announce_title_system_open(interaction, gid, uid):
        system = get_title_system(gid)
        if system.get("opened"):
            return

        system["opened"] = True
        system["opened_by"] = str(uid)
        system["opened_at"] = now_kst().strftime("%Y-%m-%d %H:%M:%S")
        if add_title_to_user(gid, uid, FIRST_COLLECTOR_TITLE):
            system["first_collector_awarded_to"] = str(uid)
            system["first_collector_title"] = FIRST_COLLECTOR_TITLE
            system["first_collector_awarded_at"] = system["opened_at"]
        channel = await get_title_notice_channel(interaction, gid)
        embed = discord.Embed(
            title="✨ 히든 퀘스트 발견!",
            description=(
                f"<@{uid}> 님이 내전 퀘스트 조건을 최초로 달성하여,\n"
                "**서버 내 [칭호 시스템]이 오픈되었습니다.**\n\n"
                "이제 특정 조건을 달성하면 숨겨진 칭호를 획득할 수 있습니다.\n"
                f"최초 발견 보상으로 **[{FIRST_COLLECTOR_TITLE}]** 칭호가 함께 지급되었습니다."
            ),
            color=0xf1c40f
        )
        embed.add_field(
            name="사용 가능한 명령어",
            value=(
                "`/칭호 작업:목록` - 보유 중인 칭호 확인\n"
                "`/칭호 작업:장착` - 칭호 장착\n"
                "`/칭호 작업:해제` - 장착 칭호 해제\n"
            ),
            inline=False
        )
        embed.set_footer(text="장착한 칭호는 /내정보 와 /전적 에서 확인할 수 있습니다.")
        await channel.send(embed=embed)
    async def announce_title_unlock(interaction, gid, uid, title, condition=None):
        await announce_title_system_open(interaction, gid, uid)
        condition = condition or get_title_unlock_condition(gid, title)
        if bot.title_batch is not None:
            bot.title_batch.setdefault(gid, []).append((str(uid), title, condition))
            return
        condition_text = format_title_condition_block(gid, title, condition)
        source_text = format_title_source_note_line(title)
        channel = await get_title_notice_channel(interaction, gid)
        embed = discord.Embed(
            title=f"🏷️ {TITLE_SEASON_LABELS[TITLE_CURRENT_SEASON]} 퀘스트 달성!",
            description=(
                f"<@{uid}> 님이 새로운 칭호를 획득했습니다.\n\n"
                f"획득 칭호\n**[{title}]**{source_text}\n\n"
                f"{condition_text}"
                "`/칭호 작업:목록`에서 확인하고 `/칭호 작업:장착`으로 장착해보세요."
            ),
            color=0x9b59b6
        )
        await channel.send(embed=embed)
    async def announce_first_title_unlock(interaction, gid, uid, title, condition=None):
        await announce_title_system_open(interaction, gid, uid)
        condition = condition or get_title_unlock_condition(gid, title)
        if bot.title_batch is not None:
            bot.title_batch.setdefault(gid, []).append((str(uid), f"{title} · 서버 최초 한정", condition))
            return
        condition_text = format_title_condition_block(gid, title, condition)
        source_text = format_title_source_note_line(title)
        channel = await get_title_notice_channel(interaction, gid)
        embed = discord.Embed(
            title=f"🌟 {TITLE_SEASON_LABELS[TITLE_CURRENT_SEASON]} 서버 최초 한정 칭호 획득!",
            description=(
                f"<@{uid}> 님이 서버에서 최초로 조건을 달성했습니다.\n\n"
                f"획득 칭호\n**[{title}]**{source_text}\n\n"
                f"{condition_text}"
                "이 칭호는 **최초 달성자만 보유할 수 있습니다.**\n"
                "`/칭호 작업:목록`에서 확인하고 `/칭호 작업:장착`으로 장착해보세요."
            ),
            color=0xf1c40f
        )
        await channel.send(embed=embed)
    async def grant_first_title(interaction, gid, uid, key):
        if not is_feature_enabled(gid, "titles"):
            return False
        title_info = FIRST_TITLE_DEFS[key]
        title = title_info["title"]
        if not mark_first_title_claimed(gid, key, uid, title):
            return False
        add_title_to_user(gid, uid, title)
        await announce_first_title_unlock(interaction, gid, uid, title, title_info.get("condition"))
        return True
    async def grant_first_team_title(interaction, gid, uids, key):
        if not is_feature_enabled(gid, "titles"):
            return False
        if not uids:
            return False

        title_info = FIRST_TITLE_DEFS[key]
        title = title_info["title"]
        condition = title_info.get("condition")
        if not mark_first_title_claimed(gid, key, uids[0], title):
            return False

        for uid in uids:
            add_title_to_user(gid, uid, title)

        await announce_title_system_open(interaction, gid, uids[0])
        if bot.title_batch is not None:
            for uid in uids:
                bot.title_batch.setdefault(gid, []).append((str(uid), f"{title} · 서버 최초 한정", condition))
            return True
        channel = await get_title_notice_channel(interaction, gid)
        mentions = " ".join(f"<@{uid}>" for uid in uids)
        condition_text = format_title_condition_block(gid, title, condition)
        source_text = format_title_source_note_line(title)
        embed = discord.Embed(
            title="🏷️ 팀 퀘스트 달성!",
            description=(
                f"{mentions}\n\n새로운 칭호를 획득했습니다.\n\n"
                f"획득 칭호\n**[{title}]**{source_text}\n\n"
                f"{condition_text}"
                "이 칭호는 **최초 달성팀만 보유할 수 있습니다.**\n"
                "`/칭호 작업:목록`에서 확인하고 `/칭호 작업:장착`으로 장착해보세요."
            ),
            color=0x9b59b6
        )
        await channel.send(embed=embed)
        return True
    async def grant_title(interaction, gid, uid, title):
        if not is_feature_enabled(gid, "titles"):
            return False
        if not add_title_to_user(gid, uid, title):
            return False
        await announce_title_unlock(interaction, gid, uid, title)
        return True
    CHAMPION_MASTERY_TITLE_STEPS = (
        (10, "{champion}의 길을 걷는 자", "여정의 시작 {champion}"),
        (15, "{champion:euro} 증명한 자", "{champion}의 이름을 새긴 자"),
        (20, "{champion} 그 자체", "{champion}의 원조"),
    )
    CHAMPION_MASTERY_TITLE_OVERRIDES = {
        ("알리스타", 10, "first"): "내가 길을 알아",
        ("럼블", 10, "first"): "하늘을 뚫는 드릴",
        ("진", 10, "first"): "아직 한 발 남았다",
        ("가렌", 10, "first"): "데마시아의 정의",
        ("갱플랭크", 10, "first"): "혀어어어업상",
        ("그레이브즈", 10, "first"): "땅땅땅 빵!",
        ("그웬", 10, "first"): "싹둑싹둑!",
        ("노틸러스", 10, "first"): "물이깊으니 조심해",
        ("드레이븐", 10, "first"): "드레이븐의 리그!",
        ("라이즈", 10, "first"): "룬 마법사",
        ("람머스", 10, "first"): "그래.",
        ("럭스", 10, "first"): "빛으로 강타해요!",
        ("루시안", 10, "first"): "세나의 복수다",
        ("리 신", 10, "first"): "이쿠!",
        ("리산드라", 10, "first"): "얼어붙어라",
        ("릴리아", 10, "first"): "잘자요~",
        ("말파이트", 10, "first"): "멈출수없는힘",
        ("모데카이저", 10, "first"): "진실의방으로",
        ("바이", 10, "first"): "정지 명령.",
        ("브라움", 10, "first"): "나만 믿으라구!",
        ("사이온", 10, "first"): "빙그르르 빵!",
        ("소라카", 10, "first"): "어머니의 손길",
        ("쉔", 10, "first"): "이즈한테일단궁썼어",
        ("스몰더", 10, "first"): "엄마ㅏㅏㅏ",
        ("아지르", 10, "first"): "사막의 황제",
        ("아트록스", 10, "first"): "다르킨의 검",
        ("에코", 10, "first"): "시공간붕괴 !",
        ("오른", 10, "first"): "대장장이의 신",
        ("이즈리얼", 10, "first"): "신비한 화살",
        ("자크", 10, "first"): "뚜루뚜빠라빠라",
        ("제드", 10, "first"): "보이지 않는 검",
        ("제리", 10, "first"): "찌릿찌릿!",
        ("직스", 10, "first"): "폭탄 전문가",
        ("징크스", 10, "first"): "신난다!",
        ("카서스", 10, "first"): "가게 두어라",
        ("케이틀린", 10, "first"): "저격수",
        ("코르키", 10, "first"): "상황 파악 끝!",
        ("크산테", 10, "first"): '"그 긴거"',
        ("클레드", 10, "first"): "버럭버럭!",
        ("탈론", 10, "first"): "벽 넘기 장인",
        ("탈리야", 10, "first"): "바위술사",
        ("탐 켄치", 10, "first"): "낼름낼름",
        ("트런들", 10, "first"): "트롤한판해볼까!",
        ("트위스티드 페이트", 10, "first"): "카드 마스터",
        ("피즈", 10, "first"): "밥먹자!",
    }
    MULTI_CHAMPION_MASTERY_TITLES = {
        "과학 시간": ("야스오", "요네"),
    }
    def has_final_consonant(text):
        text = str(text or "").strip()
        if not text:
            return False
        code = ord(text[-1])
        if 0xAC00 <= code <= 0xD7A3:
            return (code - 0xAC00) % 28 != 0
        return False
    def get_euro_particle(text):
        return "으로" if has_final_consonant(text) else "로"
    def format_champion_title(template, champion):
        champion = str(champion or "").strip()
        if "{champion:euro}" in template:
            return template.replace("{champion:euro}", f"{champion}{get_euro_particle(champion)}")
        return template.format(champion=champion)
    def get_champion_mastery_title_override(champion, games, kind):
        champion_key = normalize_champion_title_key(champion)
        kind = str(kind or "").strip()
        for override_champion, override_games, override_kind in CHAMPION_MASTERY_TITLE_OVERRIDES:
            if (
                champion_key == normalize_champion_title_key(override_champion)
                and int(games) == int(override_games)
                and kind == override_kind
            ):
                return CHAMPION_MASTERY_TITLE_OVERRIDES[(override_champion, override_games, override_kind)]
        return None
    def format_champion_mastery_title(champion, games, kind, template):
        override = get_champion_mastery_title_override(champion, games, kind)
        if override:
            return override
        return format_champion_title(template, champion)
    def extract_champion_from_title_template(title, template):
        marker = "{champion}"
        if marker in template:
            prefix, suffix = template.split(marker, 1)
            if title.startswith(prefix) and title.endswith(suffix):
                return title[len(prefix):len(title) - len(suffix) if suffix else None]
            return None

        euro_marker = "{champion:euro}"
        if euro_marker in template:
            prefix, suffix = template.split(euro_marker, 1)
            if not title.startswith(prefix) or not title.endswith(suffix):
                return None
            middle = title[len(prefix):len(title) - len(suffix) if suffix else None]
            for particle in ("으로", "로"):
                if middle.endswith(particle):
                    return middle[:-len(particle)]
        return None
    def normalize_champion_title_key(champion):
        return re.sub(r"\s+", "", str(champion or "").strip().lower())
    def is_trackable_champion_name(champion):
        text = str(champion or "").strip()
        if not text:
            return False
        blocked = {"미입력", "미확정", "챔피언 없음", "챔피언 미확정", "unknown", "none", "null"}
        if text.lower() in blocked:
            return False
        return "?" not in text
    def _normalize_record_time_for_s2(dt):
        if not isinstance(dt, datetime):
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    def is_s2_title_record(record):
        if not isinstance(record, dict):
            return False
        dt = _normalize_record_time_for_s2(parse_history_time(record))
        return bool(dt and dt >= TITLE_S2_RECORD_START)
    def get_s2_match_ids(gid):
        return {
            str(record.get("id"))
            for record in get_valid_match_history(gid)
            if record.get("id") and is_s2_title_record(record)
        }
    def get_s2_champion_mastery_rows(gid, uid):
        """Champion stats used by S2 title progress only. Pre-S2 games are excluded."""
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        valid_ids = get_s2_match_ids(gid)
        buckets = {}

        for entry in match_stats.iter_entries(guild_data, user_id=uid):
            if str(entry.get("match_id") or "") not in valid_ids:
                continue
            champion = str(entry.get("champion") or "").strip()
            if not is_trackable_champion_name(champion):
                continue
            key = normalize_champion_title_key(champion)
            bucket = buckets.setdefault(key, {
                "label": champion,
                "games": 0,
                "wins": 0,
                "losses": 0,
            })
            bucket["games"] += 1
            result = str(entry.get("result") or "").strip().lower()
            if result == "win":
                bucket["wins"] += 1
            elif result == "loss":
                bucket["losses"] += 1

        rows = list(buckets.values())
        for row in rows:
            games = int(row.get("games", 0) or 0)
            row["win_rate"] = (int(row.get("wins", 0) or 0) / games * 100) if games else 0.0
        rows.sort(key=lambda row: (-int(row.get("games", 0) or 0), str(row.get("label") or "")))
        return rows
    def get_champion_mastery_title_condition(title):
        title = str(title or "").strip()
        if not title:
            return None
        if title == "과학 시간":
            return "시즌 2 야스오+요네 상세스탯 합계 20판 이상 + 합산 승률 60% 이상 서버 최초 달성"
        for (champion, games, kind), override_title in CHAMPION_MASTERY_TITLE_OVERRIDES.items():
            if title == override_title:
                if kind == "first":
                    return f"시즌 2 {champion} 상세스탯 {games}판 이상 + 승률 60% 이상 서버 최초 달성"
                return f"시즌 2 {champion} 상세스탯 {games}판 달성"
        for games, normal_template, first_template in CHAMPION_MASTERY_TITLE_STEPS:
            champion = extract_champion_from_title_template(title, normal_template)
            if champion:
                return f"시즌 2 {champion} 상세스탯 {games}판 달성"

            champion = extract_champion_from_title_template(title, first_template)
            if champion:
                return f"시즌 2 {champion} 상세스탯 {games}판 이상 + 승률 60% 이상 서버 최초 달성"
        return None
    async def grant_first_champion_mastery_title(interaction, gid, uid, champion, games, title):
        key = f"champion_mastery:{games}:{normalize_champion_title_key(champion)}"
        if not mark_first_title_claimed(gid, key, uid, title):
            return False
        add_title_to_user(gid, uid, title)
        await announce_first_title_unlock(
            interaction,
            gid,
            uid,
            title,
            f"시즌 2 {champion} 상세스탯 {games}판 이상 + 승률 60% 이상 서버 최초 달성"
        )
        return True
    async def check_champion_mastery_titles(interaction, gid, uid):
        guild_data = bot.user_data.setdefault(gid, {})
        ensure_user_format(guild_data.setdefault(str(uid), make_default_user(f"UID {uid}")))
        rows = get_s2_champion_mastery_rows(gid, uid)
        changed = False

        # Every champion-mastery title in S2 counts S2 detailed games only.
        # First-limited titles additionally require a S2 win rate of at least 60%.
        for row in rows:
            champion = str(row.get("label") or "").strip()
            if not is_trackable_champion_name(champion):
                continue
            games = int(row.get("games", 0) or 0)
            win_rate = float(row.get("win_rate", 0) or 0)
            for threshold, normal_template, first_template in CHAMPION_MASTERY_TITLE_STEPS:
                if games < threshold:
                    continue
                normal_title = format_champion_mastery_title(champion, threshold, "normal", normal_template)
                changed = await grant_title(interaction, gid, uid, normal_title) or changed

                if win_rate < 60.0:
                    continue
                first_title = format_champion_mastery_title(champion, threshold, "first", first_template)
                changed = await grant_first_champion_mastery_title(
                    interaction,
                    gid,
                    uid,
                    champion,
                    threshold,
                    first_title
                ) or changed

        # 과학 시간: Yasuo + Yone combined 20 S2 games, combined WR >= 60%, server first.
        science_rows = {
            normalize_champion_title_key(row.get("label")): row
            for row in rows
        }
        science_games = 0
        science_wins = 0
        for champion in ("야스오", "요네"):
            row = science_rows.get(normalize_champion_title_key(champion)) or {}
            science_games += int(row.get("games", 0) or 0)
            science_wins += int(row.get("wins", 0) or 0)
        science_wr = (science_wins / science_games * 100) if science_games else 0.0
        if science_games >= 20 and science_wr >= 60.0:
            title = "과학 시간"
            key = "champion_mastery_combo:science_time:yasuo_yone:20"
            if mark_first_title_claimed(gid, key, uid, title):
                add_title_to_user(gid, uid, title)
                await announce_first_title_unlock(
                    interaction,
                    gid,
                    uid,
                    title,
                    "시즌 2 야스오+요네 상세스탯 합계 20판 이상 + 합산 승률 60% 이상 서버 최초 달성"
                )
                changed = True

        # ShowMaker Challenge: play 80 distinct champions in S2. One game per champion is enough.
        distinct_champions = sum(1 for row in rows if int(row.get("games", 0) or 0) >= 1)
        if distinct_champions >= 80:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["showmaker_challenge"]) or changed

        return changed
    async def check_champion_mastery_titles_for_entries(interaction, gid, entries):
        changed = False
        seen_uids = {
            str(entry.get("user_id"))
            for entry in entries
            if entry.get("user_id") is not None
        }
        for uid in seen_uids:
            changed = await check_champion_mastery_titles(interaction, gid, uid) or changed
        return changed
    def get_detail_award_counts(gid, uid):
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        counts = {"mvp_count": 0, "ace_count": 0}
        for match_id in list(match_stats.get_store(guild_data).keys()):
            try:
                awards = match_stats.score_match_awards(guild_data, match_id)
            except Exception:
                logger.exception("수상 칭호 경기 수상 계산 실패: %s", match_id)
                continue
            if str((awards.get("mvp") or {}).get("user_id")) == uid:
                counts["mvp_count"] += 1
            if str((awards.get("ace") or {}).get("user_id")) == uid:
                counts["ace_count"] += 1
        counts["total"] = counts["mvp_count"] + counts["ace_count"]
        return counts
    def get_s2_detail_award_counts(gid, uid):
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        counts = {"mvp_count": 0, "ace_count": 0}
        for record in get_valid_match_history(gid):
            if not is_s2_title_record(record):
                continue
            match_id = str(record.get("id") or "")
            if not match_id or not match_stats.get_store(guild_data).get(match_id):
                continue
            try:
                awards = match_stats.score_match_awards(guild_data, match_id)
            except Exception:
                logger.exception("S2 수상 포인트 칭호 계산 실패: %s", match_id)
                continue
            if str((awards.get("mvp") or {}).get("user_id")) == uid:
                counts["mvp_count"] += 1
            if str((awards.get("ace") or {}).get("user_id")) == uid:
                counts["ace_count"] += 1
        counts["total"] = counts["mvp_count"] + counts["ace_count"]
        return counts
    def get_league_final_award_counts(gid, uid):
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        final_match_ids = [
            str(record.get("id"))
            for record in get_valid_match_history(gid)
            if (
                (
                    record.get("mode") == LEAGUE_MODE_KEY
                    and safe_detail_int(record.get("match_no")) == 3
                )
                or (
                    record.get("mode") == LEAGUE_SERIES_MODE_KEY
                    and str(record.get("round_name") or "").strip() == "결승"
                )
            )
            and record.get("id")
        ]
        counts = {"mvp_count": 0, "ace_count": 0}
        for match_id in final_match_ids:
            if not match_stats.get_store(guild_data).get(match_id):
                continue
            try:
                awards = match_stats.score_match_awards(guild_data, match_id)
            except Exception:
                logger.exception("토너먼트 결승 수상 칭호 계산 실패: %s", match_id)
                continue
            if str((awards.get("mvp") or {}).get("user_id")) == uid:
                counts["mvp_count"] += 1
            if str((awards.get("ace") or {}).get("user_id")) == uid:
                counts["ace_count"] += 1
        return counts
    async def check_detail_award_titles(interaction, gid, uid):
        counts = get_detail_award_counts(gid, uid)
        s2_counts = get_s2_detail_award_counts(gid, uid)
        league_final_counts = get_league_final_award_counts(gid, uid)
        changed = False

        if counts["mvp_count"] >= 10:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["mvp_10"]) or changed
            changed = await grant_first_title(interaction, gid, uid, "first_mvp_10") or changed
        if counts["ace_count"] >= 10:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["ace_10"]) or changed
            changed = await grant_first_title(interaction, gid, uid, "first_ace_10") or changed
        # These point thresholds are S2 revisions, so pre-S2 awards do not count.
        s2_award_points = s2_counts["mvp_count"] * 100 + s2_counts["ace_count"] * 50
        if s2_award_points >= 1000:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["award_20"]) or changed
        if s2_award_points >= 2000:
            changed = await grant_first_title(interaction, gid, uid, "first_award_30") or changed
        if league_final_counts["mvp_count"] >= 1:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["league_final_mvp_1"]) or changed
        if league_final_counts["mvp_count"] >= 3:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["league_final_mvp_3"]) or changed
        if league_final_counts["ace_count"] >= 1:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["league_final_ace_1"]) or changed
        if league_final_counts["ace_count"] >= 3:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["league_final_ace_3"]) or changed

        return changed
    async def check_detail_award_titles_for_entries(interaction, gid, entries):
        changed = False
        seen_uids = {
            str(entry.get("user_id"))
            for entry in entries
            if entry.get("user_id") is not None
        }
        for uid in seen_uids:
            changed = await check_detail_award_titles(interaction, gid, uid) or changed
        return changed
    async def check_detail_award_titles_for_match(interaction, gid, match_id):
        guild_data = bot.user_data.setdefault(gid, {})
        match_entries = match_stats.get_store(guild_data).get(str(match_id), {}) or {}
        return await check_detail_award_titles_for_entries(interaction, gid, list(match_entries.values()))
    def _entry_objective_steal_count(entry):
        info = entry.get("objective_steal") if isinstance(entry, dict) else None
        if isinstance(info, dict):
            return int(info.get("count", 0) or 0)
        rofl_stats = entry.get("rofl_stats") if isinstance(entry, dict) else None
        if isinstance(rofl_stats, dict):
            return int(rofl_stats.get("OBJECTIVES_STOLEN", 0) or 0)
        return 0
    def get_confirmed_objective_steal_totals(gid, uid):
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        totals = {"DRAGON": 0, "BARON": 0, "ELDER": 0, "HERALD": 0, "ALL": 0}
        valid_ids = get_s2_match_ids(gid)
        for match_id, match_entries in match_stats.get_store(guild_data).items():
            if str(match_id) not in valid_ids:
                continue
            entry = (match_entries or {}).get(uid)
            if not entry:
                continue
            totals["ALL"] += _entry_objective_steal_count(entry)
            info = entry.get("objective_steal")
            if not isinstance(info, dict) or info.get("confidence") != "confirmed":
                continue
            for objective, count in (info.get("objective_counts") or {}).items():
                key = str(objective).upper()
                if key in totals:
                    totals[key] += int(count or 0)
        return totals
    def get_user_ai_score_history(gid, uid):
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        score_by_match = {}
        for record in get_valid_match_history(gid):
            if not is_s2_title_record(record):
                continue
            match_id = str(record.get("id") or "")
            if not match_id or uid not in (match_stats.get_store(guild_data).get(match_id, {}) or {}):
                continue
            awards = match_stats.score_match_awards(guild_data, match_id)
            row = next((item for item in awards.get("scores", []) if str(item.get("user_id")) == uid), None)
            if not row:
                continue
            score_by_match[match_id] = {
                "record": record,
                "entry": match_stats.get_store(guild_data)[match_id][uid],
                "score": float(row.get("display_score", row.get("expectation_score", row.get("score", 0))) or 0),
                "award_row": row,
                "awards": awards,
            }
        rows = list(score_by_match.values())
        rows.sort(key=lambda item: parse_history_time(item["record"]))
        return rows
    def _record_kst_date(record):
        dt = parse_history_time(record)
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            else:
                dt = dt.astimezone(KST)
            return dt.date()
        return None
    def _team_average_before_mmr(record, team):
        values = [int(p.get("before_mmr", 0) or 0) for p in (record.get("players", []) or []) if p.get("team") == team and int(p.get("before_mmr", 0) or 0) > 0]
        return sum(values) / len(values) if values else 0.0
    async def check_s2_detail_titles(interaction, gid, uid):
        """Award S2 ROFL/AI/objective titles from persisted detailed stats.

        Objective-specific titles fail closed: only objective_steal confidence=confirmed
        contributes to Dragon/Baron counters.
        """
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        changed = False

        steal_totals = get_confirmed_objective_steal_totals(gid, uid)
        if steal_totals["ALL"] >= 1:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["objective_steal_1"]) or changed
        if steal_totals["BARON"] >= 1:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["baron_steal_1"]) or changed
        if steal_totals["BARON"] >= 3:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["baron_steal_3"]) or changed
        if steal_totals["BARON"] >= 5:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["baron_steal_5"]) or changed
        if steal_totals["DRAGON"] >= 3:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["dragon_steal_3"]) or changed
        if steal_totals["DRAGON"] >= 10:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["dragon_steal_10"]) or changed

        history = get_user_ai_score_history(gid, uid)
        if not history:
            return changed

        latest = history[-1]
        score = latest["score"]
        entry = latest["entry"]
        record = latest["record"]
        awards = latest["awards"]

        if score >= 120:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["ai_120"]) or changed
            changed = await grant_first_title(interaction, gid, uid, "first_ai_120") or changed
        if score >= 130:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["ai_130"]) or changed
        if len(history) >= 5 and sum(item["score"] for item in history[-5:]) / 5 >= 100:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["ai_recent5_avg100"]) or changed
        if len(history) >= 10 and sum(item["score"] for item in history[-10:]) / 10 >= 100:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["ai_recent10_avg100"]) or changed

        if len(history) >= 2:
            prev = history[-2]
            if (
                _record_kst_date(prev["record"]) == _record_kst_date(record)
                and prev["score"] >= 110
                and score >= 110
            ):
                changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["ai_two_110_same_day"]) or changed

        if entry.get("result") == "win" and int(entry.get("deaths", 0) or 0) == 0 and score >= 100:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["clean_game"]) or changed
        if entry.get("result") == "win" and int(entry.get("kills", 0) or 0) >= 15:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["kills_15_win"]) or changed
        if (
            entry.get("result") == "win"
            and float(entry.get("kill_participation", 0) or 0) >= 80
            and int(entry.get("kills", 0) or 0) + int(entry.get("assists", 0) or 0) >= 10
        ):
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["kp_80_win"]) or changed

        opponent = None
        for other in (match_stats.get_store(guild_data).get(str(record.get("id")), {}) or {}).values():
            if str(other.get("user_id")) != uid and other.get("role") == entry.get("role") and other.get("team") != entry.get("team"):
                opponent = other
                break
        if entry.get("result") == "win" and opponent:
            duration_seconds = resolve_detail_duration_seconds(guild_data, record, uid=uid)
            if (
                duration_seconds >= 20 * 60
                and float(entry.get("gpm", 0) or 0) - float(opponent.get("gpm", 0) or 0) >= 180
            ):
                changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["gpm_lane_100_win"]) or changed

        if str((awards.get("mvp") or {}).get("user_id")) == uid:
            if int(entry.get("opponent_mmr", 0) or 0) - int(entry.get("before_mmr", 0) or 0) >= 600:
                changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["lane_gap_mvp_600"]) or changed

        if entry.get("result") == "win" and score >= 110:
            team = entry.get("team")
            other_team = "red" if team == "blue" else "blue" if team == "red" else None
            if other_team:
                own_avg = _team_average_before_mmr(record, team)
                opp_avg = _team_average_before_mmr(record, other_team)
                if own_avg > 0 and opp_avg - own_avg >= 300:
                    changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["underdog_ai_110"]) or changed

        # Same-KST-day MVP count.
        latest_date = _record_kst_date(record)
        if latest_date:
            daily_mvp = 0
            for item in history:
                if _record_kst_date(item["record"]) != latest_date:
                    continue
                if str((item["awards"].get("mvp") or {}).get("user_id")) == uid:
                    daily_mvp += 1
            if daily_mvp >= 3:
                changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["daily_mvp_2"]) or changed

        return changed
    async def check_s2_detail_titles_for_entries(interaction, gid, entries):
        changed = False
        for uid in sorted({str(entry.get("user_id")) for entry in entries if entry.get("user_id") is not None}):
            changed = await check_s2_detail_titles(interaction, gid, uid) or changed
        return changed
    def get_penta_kill_count(gid, uid):
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        total = 0
        for match_entries in match_stats.get_store(guild_data).values():
            entry = (match_entries or {}).get(uid)
            if not entry:
                continue
            total += int(entry.get("penta_kills", 0) or 0)
        return total
    async def check_penta_kill_titles(interaction, gid, uid):
        total = get_penta_kill_count(gid, uid)
        changed = False
        if total >= 1:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["penta_1"]) or changed
            changed = await grant_first_title(interaction, gid, uid, "first_penta_kill") or changed
        if total >= 3:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["penta_3"]) or changed
        if total >= 5:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["penta_5"]) or changed
        if total >= 10:
            changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["penta_10"]) or changed
        return changed
    async def check_penta_kill_titles_for_entries(interaction, gid, entries):
        changed = False
        seen_uids = {
            str(entry.get("user_id"))
            for entry in entries
            if entry.get("user_id") is not None and int(entry.get("penta_kills", 0) or 0) > 0
        }
        for uid in seen_uids:
            changed = await check_penta_kill_titles(interaction, gid, uid) or changed
        return changed
    def has_zero_death_win_streak(gid, uid, required_streak=2):
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        streak = 0
        detail_store = match_stats.get_store(guild_data)

        for record in sorted(get_valid_match_history(gid), key=parse_history_time):
            entry = detail_store.get(str(record.get("id")), {}).get(uid)
            if not entry:
                continue
            if entry.get("result") == "win" and int(entry.get("deaths", 0) or 0) == 0:
                streak += 1
                if streak >= required_streak:
                    return True
            else:
                streak = 0
        return False
    async def check_zero_death_titles(interaction, gid, uid):
        guild_data = bot.user_data.setdefault(gid, {})
        uid = str(uid)
        changed = False

        for entry in match_stats.iter_entries(guild_data, user_id=uid):
            if entry.get("result") == "loss" and int(entry.get("deaths", 0) or 0) == 0:
                changed = await grant_first_title(interaction, gid, uid, "first_zero_death_loss") or changed
                break

        if has_zero_death_win_streak(gid, uid, 2):
            changed = await grant_first_title(interaction, gid, uid, "first_zero_death_win_streak_2") or changed

        return changed
    async def check_zero_death_titles_for_entries(interaction, gid, entries):
        changed = False
        seen_uids = {
            str(entry.get("user_id"))
            for entry in entries
            if entry.get("user_id") is not None
        }
        for uid in seen_uids:
            changed = await check_zero_death_titles(interaction, gid, uid) or changed
        return changed
    async def check_zero_death_titles_for_match(interaction, gid, match_id):
        guild_data = bot.user_data.setdefault(gid, {})
        match_entries = match_stats.get_store(guild_data).get(str(match_id), {}) or {}
        return await check_zero_death_titles_for_entries(interaction, gid, list(match_entries.values()))
    async def check_queue_lineup_titles(interaction, gid, queue_key, queue_entries):
        required_count = get_required_count(queue_key)
        if required_count != 10 or queue_key in (ARENA_QUEUE_NUM, LEAGUE_QUEUE_KEY):
            return False
        if len(queue_entries) < required_count:
            return False

        changed = False
        start_user = normalize_queue_entry(queue_entries[0])[0]
        final_user = normalize_queue_entry(queue_entries[required_count - 1])[0]

        if start_user:
            uid = str(start_user.id)
            user_info = ensure_user_format(bot.user_data.setdefault(gid, {}).setdefault(uid, make_default_user(getattr(start_user, "display_name", f"UID {uid}"))))
            stats = user_info.setdefault('queue_title_stats', {})
            stats['start_count'] = int(stats.get('start_count', 0) or 0) + 1
            changed = True
            if stats['start_count'] >= 10:
                changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["queue_start_5"]) or changed
            if stats['start_count'] >= 30:
                changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["queue_start_15"]) or changed

        if final_user:
            uid = str(final_user.id)
            user_info = ensure_user_format(bot.user_data.setdefault(gid, {}).setdefault(uid, make_default_user(getattr(final_user, "display_name", f"UID {uid}"))))
            stats = user_info.setdefault('queue_title_stats', {})
            stats['final_count'] = int(stats.get('final_count', 0) or 0) + 1
            changed = True
            if stats['final_count'] >= 10:
                changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["queue_final_5"]) or changed
            if stats['final_count'] >= 30:
                changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["queue_final_15"]) or changed

        if changed:
            bot.save_lucid_data(gid)

        return changed
    def get_auto_custom_title_name(guild, gid, uid):
        user_info = ensure_user_format(
            bot.user_data.setdefault(gid, {}).setdefault(str(uid), make_default_user(f"UID {uid}"))
        )
        riot_name = compact_riot_name(user_info.get("lol_name", ""))
        if riot_name:
            return riot_name
        fallback = compact_riot_name(get_member_display_name(guild, gid, uid))
        return fallback or f"소환사 {uid}"
    def finalize_legacy_pending_custom_titles(guild, gid, uid):
        """이름입력 방식으로 남아 있는 구형 특별칭호를 Riot ID 닉네임으로 자동 확정한다."""
        user_info = ensure_user_format(
            bot.user_data.setdefault(gid, {}).setdefault(str(uid), make_default_user(f"UID {uid}"))
        )
        titles = user_info["titles"]
        pending = list(titles.get("pending_custom", []) or [])
        if not pending and titles.get("pending_dynasty"):
            pending = [{
                "kind": "dynasty",
                "template": "🥇 {name}의 왕조",
                "display_name": "왕조",
                "season": TITLE_LEGACY_SEASON,
            }]

        if not pending:
            return False

        changed = False
        global_achieved = titles.setdefault("achieved_custom", [])
        for item in pending:
            kind = str(item.get("kind", "custom"))
            season = str(item.get("season") or TITLE_LEGACY_SEASON)
            if kind.startswith("duo:"):
                partner_uid = kind.split(":", 1)[1]
                title_name = get_auto_custom_title_name(guild, gid, partner_uid)
            else:
                title_name = get_auto_custom_title_name(guild, gid, uid)
            template = str(item.get("template") or "🏷️ {name}의 칭호")
            title = template.format(name=title_name)
            if add_title_to_user(gid, uid, title, season=season):
                changed = True
            if kind not in global_achieved:
                global_achieved.append(kind)
                changed = True
            season_achieved = get_title_season_bucket(user_info, season).setdefault("achieved_custom", [])
            if kind not in season_achieved:
                season_achieved.append(kind)
                changed = True

        titles["pending_dynasty"] = None
        titles["pending_custom"] = []
        if changed:
            bot.save_lucid_data(gid)
        return changed
    async def set_pending_custom_title(interaction, gid, uid, kind, template, display_name, first_limited=False, title_name=None):
        """특별칭호를 해금 즉시 Riot ID의 # 앞 닉네임으로 자동 생성한다.

        함수명은 기존 호출부 호환을 위해 유지하지만 더 이상 입력 대기 상태를 만들지 않는다.
        """
        if not is_feature_enabled(gid, "titles"):
            return False
        user_info = ensure_user_format(bot.user_data[gid][str(uid)])
        season_bucket = get_title_season_bucket(user_info, TITLE_CURRENT_SEASON)
        achieved = season_bucket.setdefault("achieved_custom", [])
        if kind in achieved:
            return False

        if title_name is None:
            title_name = get_auto_custom_title_name(getattr(interaction, "guild", None), gid, uid)
        else:
            title_name = compact_riot_name(title_name) or str(title_name).strip()
        if not title_name:
            title_name = get_auto_custom_title_name(getattr(interaction, "guild", None), gid, uid)

        title = template.format(name=title_name)
        added = add_title_to_user(gid, uid, title, season=TITLE_CURRENT_SEASON)
        if not added and title not in user_info["titles"].setdefault("owned", []):
            return False

        achieved.append(kind)
        global_achieved = user_info["titles"].setdefault("achieved_custom", [])
        if kind not in global_achieved:
            global_achieved.append(kind)

        # 구형 입력대기 데이터가 같은 칭호로 남아 있으면 함께 정리한다.
        user_info["titles"]["pending_custom"] = [
            item for item in user_info["titles"].get("pending_custom", [])
            if str(item.get("kind")) != str(kind)
        ]
        if kind == "dynasty":
            user_info["titles"]["pending_dynasty"] = None

        # 서버 최초 claim에 실제 완성된 칭호명을 기록한다.
        claim_key = {
            "event_legend": "first_event_legend",
            "first_low_tier_3_streak": "first_low_tier_3_streak",
        }.get(str(kind))
        if claim_key:
            claim = get_title_season_claims(gid, TITLE_CURRENT_SEASON).get(claim_key)
            if isinstance(claim, dict) and str(claim.get("user_id")) == str(uid):
                claim["title"] = title

        bot.save_lucid_data(gid)
        await announce_title_system_open(interaction, gid, uid)
        condition = get_custom_title_unlock_condition(gid, kind, display_name)
        if bot.title_batch is not None:
            suffix = " · 서버 최초 한정" if first_limited else ""
            bot.title_batch.setdefault(gid, []).append((str(uid), f"{title}{suffix}", condition))
            return True

        channel = await get_title_notice_channel(interaction, gid)
        condition_text = f"달성 조건\n`{condition}`\n\n" if condition else ""
        embed = discord.Embed(
            title="👑 특별 칭호 획득!",
            description=(
                f"<@{uid}> 님, 특별 칭호를 획득했습니다.\n\n"
                f"{condition_text}"
                f"획득 칭호\n**[{title}]**\n\n"
                + ("이 칭호는 **최초 달성자만 보유할 수 있습니다.**\n\n" if first_limited else "")
                + "`/칭호 작업:장착`에서 바로 장착할 수 있습니다."
            ),
            color=0xf1c40f
        )
        await channel.send(embed=embed)
        return True
    async def flush_title_batch(interaction, gid):
        if not bot.title_batch or not bot.title_batch.get(gid):
            if bot.title_batch is not None:
                bot.title_batch.pop(gid, None)
                if not bot.title_batch:
                    bot.title_batch = None
            return

        seen = set()
        lines = []
        for item in bot.title_batch.get(gid, []):
            if len(item) >= 3:
                uid, title, condition = item[:3]
            else:
                uid, title = item[:2]
                condition = get_title_unlock_condition(gid, title.replace(" · 서버 최초 한정", ""))
            key = (uid, title)
            if key in seen:
                continue
            seen.add(key)
            clean_title = title.replace(" · 서버 최초 한정", "")
            source_text = format_title_source_note_line(clean_title)
            summary = format_title_condition_summary(gid, clean_title, condition)
            condition_text = f"\n{summary}" if summary else ""
            lines.append(f"<@{uid}> - **[{title}]**{source_text}{condition_text}")

        bot.title_batch.pop(gid, None)
        if not bot.title_batch:
            bot.title_batch = None
        if not lines:
            return

        try:
            channel = await get_title_notice_channel(interaction, gid)
        except Exception:
            logger.exception("타이틀 배치 알림 채널 조회 실패: guild_id=%s", gid)
            return
        embed = discord.Embed(
            title="🏷️ 퀘스트 달성!",
            description=(
                "\n".join(lines[:25])
                + "\n\n`/칭호 작업:목록`에서 확인하고 `/칭호 작업:장착`으로 장착해보세요."
            ),
            color=0x9b59b6
        )
        try:
            await channel.send(embed=embed)
        except Exception:
            logger.exception("타이틀 배치 알림 전송 실패: guild_id=%s", gid)
    async def set_pending_dynasty_title(interaction, gid, uid):
        user_info = ensure_user_format(bot.user_data[gid][str(uid)])
        if any(str(title).endswith("의 왕조") for title in get_title_season_owned(user_info, TITLE_CURRENT_SEASON)):
            return False
        return await set_pending_custom_title(interaction, gid, uid, "dynasty", "🥇 {name}의 왕조", "왕조")
    async def set_pending_legend_title(interaction, gid, uid):
        claims = get_title_season_claims(gid, TITLE_CURRENT_SEASON)
        if "first_event_legend" in claims:
            return False
        title = "🌟 전설의 [닉네임]"
        claims["first_event_legend"] = {
            "user_id": str(uid),
            "title": title,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S")
        }
        return await set_pending_custom_title(
            interaction,
            gid,
            uid,
            "event_legend",
            "🌟 전설의 {name}",
            "전설",
            first_limited=True
        )
    async def set_pending_low_tier_rising_star_title(interaction, gid, uid):
        claims = get_title_season_claims(gid, TITLE_CURRENT_SEASON)
        if "first_low_tier_3_streak" in claims:
            return False
        title = "🌟 라이징 스타 [닉네임]"
        claims["first_low_tier_3_streak"] = {
            "user_id": str(uid),
            "title": title,
            "time": now_kst().strftime("%Y-%m-%d %H:%M:%S")
        }
        return await set_pending_custom_title(
            interaction,
            gid,
            uid,
            "first_low_tier_3_streak",
            "🌟 라이징 스타 {name}",
            "라이징 스타",
            first_limited=True
        )
    async def set_pending_duo_title(interaction, gid, uid, partner_uid):
        partner_name = get_auto_custom_title_name(getattr(interaction, "guild", None), gid, partner_uid)
        return await set_pending_custom_title(
            interaction,
            gid,
            uid,
            f"duo:{partner_uid}",
            "🤝 {name}님과의 환상 콤비",
            f"{partner_name} 님과의 환상 콤비",
            title_name=partner_name,
        )
    def get_match_history(gid):
        return bot.user_data.get(gid, {}).get(MATCH_HISTORY_KEY, [])
    def get_relation_stats(gid, target_uid):
        target_uid = str(target_uid)
        duo_stats = defaultdict(lambda: {'games': 0, 'wins': 0, 'losses': 0})
        opponent_stats = defaultdict(lambda: {'games': 0, 'wins': 0, 'losses': 0})

        for record in get_match_history(gid):
            if record.get('cancelled'):
                continue
            if record.get('mode') == NOBAN_MODE_KEY:
                continue

            players = record.get('players', [])
            target_player = next((p for p in players if str(p.get('user_id')) == target_uid), None)
            if not target_player:
                continue

            target_team = target_player.get('team')
            target_result = target_player.get('result')
            for player in players:
                other_uid = str(player.get('user_id'))
                if other_uid == target_uid:
                    continue

                other_team = player.get('team')
                other_result = player.get('result')
                if other_team == target_team:
                    stats = duo_stats[other_uid]
                    stats['games'] += 1
                    if target_result == 'win':
                        stats['wins'] += 1
                    else:
                        stats['losses'] += 1
                elif target_result == 'win' and other_result == 'loss':
                    stats = opponent_stats[other_uid]
                    stats['games'] += 1
                    stats['wins'] += 1
                elif target_result == 'loss' and other_result == 'win':
                    stats = opponent_stats[other_uid]
                    stats['games'] += 1
                    stats['losses'] += 1

        return duo_stats, opponent_stats
    def calc_win_rate(stats):
        games = stats.get('games', 0)
        return (stats.get('wins', 0) / games * 100) if games else 0.0
    def get_saved_lol_name(gid, uid, fallback):
        data = bot.user_data.get(gid, {}).get(str(uid), {})
        if isinstance(data, dict):
            return data.get('lol_name', fallback)
        return fallback
    def normalize_lol_account_key(value):
        return re.sub(r"[\s\u200b\u200c\u200d]+", "", str(value or "").strip().lower()).replace("＃", "#")
    def get_saved_lol_account_names(gid, uid, fallback=""):
        data = bot.user_data.get(gid, {}).get(str(uid), {})
        if not isinstance(data, dict):
            return [fallback] if fallback else []
        user_info = ensure_user_format(data)
        names = [user_info.get("lol_name", fallback)]
        names.extend(user_info.get("alt_lol_names", []))
        return [str(name).strip() for name in names if str(name or "").strip()]
    def find_lol_account_owner(gid, account_name, exclude_uid=None):
        query = normalize_lol_account_key(account_name)
        if not query:
            return None, None, False
        for uid, data in iter_user_records(bot.user_data.get(gid, {})):
            if exclude_uid is not None and str(uid) == str(exclude_uid):
                continue
            user_info = ensure_user_format(data)
            main_name = str(user_info.get("lol_name") or "").strip()
            if normalize_lol_account_key(main_name) == query:
                return str(uid), main_name, False
            for alt_name in user_info.get("alt_lol_names", []):
                if normalize_lol_account_key(alt_name) == query:
                    return str(uid), alt_name, True
        return None, None, False
    def get_member_label(guild, gid, uid):
        member = guild.get_member(int(uid)) if guild else None
        if member:
            return member.mention
        return get_saved_lol_name(gid, uid, f"탈퇴한 소환사({uid})")
    def normalize_rival_search_text(value):
        return re.sub(r"\s+", "", str(value or "").strip().lower())
    def find_registered_user_by_nickname(guild, gid, nickname):
        query = normalize_rival_search_text(nickname)
        if not query:
            return None, []

        exact_matches = []
        partial_matches = []
        for uid, data in iter_user_records(bot.user_data.get(gid, {})):
            user_info = ensure_user_format(data)
            member = guild.get_member(int(uid)) if guild else None
            names = [
                user_info.get("lol_name", ""),
                member.display_name if member else "",
                member.name if member else "",
                str(uid),
            ]
            normalized_names = [normalize_rival_search_text(name) for name in names if name]
            if query in normalized_names:
                exact_matches.append(uid)
            elif any(query in name for name in normalized_names):
                partial_matches.append(uid)

        matches = exact_matches or partial_matches
        if len(matches) == 1:
            return matches[0], matches
        return None, matches[:10]
    def format_rival_record_line(guild, gid, uid, stats):
        games = int(stats.get("games", 0) or 0)
        wins = int(stats.get("wins", 0) or 0)
        losses = int(stats.get("losses", 0) or 0)
        if games <= 0:
            record = "아직 상대 전적 없음"
        else:
            record = f"**{games}전 {wins}승 {losses}패** · 승률 **{calc_win_rate(stats):.1f}%**"
        return f"{get_member_label(guild, gid, uid)}\n{record}"
    def get_custom_rival_uid(gid, uid):
        """Compatibility accessor: custom_rival_uid now stores the current automatic representative rival."""
        raw_info = bot.user_data.get(gid, {}).get(str(uid), {})
        if not isinstance(raw_info, dict):
            return None
        rival_uid = ensure_user_format(raw_info).get("custom_rival_uid")
        return str(rival_uid) if rival_uid else None
    def calculate_rival_score(stats):
        games = int(stats.get("games", 0) or 0)
        if games < RIVAL_MIN_GAMES:
            return 0.0
        winrate = calc_win_rate(stats)
        if not (RIVAL_MIN_WINRATE <= winrate <= RIVAL_MAX_WINRATE):
            return 0.0
        # 7판에서 이미 공식 라이벌 자격을 갖고, 판수가 쌓일수록 최대 100에 가까워진다.
        games_score = min(100.0, 70.0 + max(0, games - RIVAL_MIN_GAMES) * 3.0)
        # 정확한 50:50이면 100점. 35:65 경계에서는 55점.
        balance_score = max(0.0, 100.0 - abs(winrate - 50.0) * 3.0)
        return round(games_score * 0.55 + balance_score * 0.45, 1)
    def get_best_auto_rival(gid, uid):
        _, opponent_stats = get_relation_stats(gid, str(uid))
        candidates = []
        for rival_uid, stats in opponent_stats.items():
            score = calculate_rival_score(stats)
            if score <= 0:
                continue
            candidates.append((str(rival_uid), stats, score))
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                item[2],
                int(item[1].get("games", 0) or 0),
                -abs(calc_win_rate(item[1]) - 50.0),
                item[0],
            ),
            reverse=True,
        )
        rival_uid, stats, score = candidates[0]
        return {"uid": rival_uid, "stats": stats, "score": score}
    def refresh_auto_rivals(guild, gid, uids=None):
        """Recalculate one representative rival per user. Returns first-ever birth announcements only."""
        if uids is None:
            uids = [uid for uid, _ in iter_user_records(bot.user_data.get(gid, {}))]
        birth_pairs = set()
        birth_lines = []
        for raw_uid in uids:
            uid = str(raw_uid)
            raw_info = bot.user_data.get(gid, {}).get(uid)
            if not isinstance(raw_info, dict):
                continue
            user_info = ensure_user_format(raw_info)
            previous_uid = str(user_info.get("custom_rival_uid") or "") or None
            initialized = bool(user_info.get("rival_auto_initialized"))
            announced = bool(user_info.get("rival_announced_once"))
            best = get_best_auto_rival(gid, uid)
            new_uid = str(best["uid"]) if best else None
            new_score = float(best["score"]) if best else 0.0

            user_info["custom_rival_uid"] = new_uid
            user_info["rival_auto_score"] = new_score
            user_info["rival_auto_initialized"] = True

            # Keep rival_stats synced to the current representative rival for legacy title logic/UI.
            if best:
                stats = best["stats"]
                user_info["rival_stats"] = {
                    "games": int(stats.get("games", 0) or 0),
                    "wins": int(stats.get("wins", 0) or 0),
                    "losses": int(stats.get("losses", 0) or 0),
                }
            else:
                user_info["rival_stats"] = {"games": 0, "wins": 0, "losses": 0}

            if not new_uid or announced:
                continue

            # Existing historical rivals are initialized silently. If the pair has exactly crossed
            # the 7-game threshold now, treat it as a new official rival and announce it once.
            games = int((best or {}).get("stats", {}).get("games", 0) or 0)
            should_announce = initialized or games == RIVAL_MIN_GAMES
            if not should_announce and previous_uid:
                user_info["rival_announced_once"] = True
                continue
            if not should_announce:
                # Legacy data already above threshold at first patch boot: no retroactive spam.
                user_info["rival_announced_once"] = True
                continue

            user_info["rival_announced_once"] = True
            pair = tuple(sorted((uid, new_uid)))
            if pair in birth_pairs:
                continue
            birth_pairs.add(pair)
            summary = get_rival_head_to_head_summary(gid, uid, new_uid)
            left = compact_riot_name(get_registered_display_name(guild, gid, uid)) or get_registered_display_name(guild, gid, uid)
            right = compact_riot_name(get_registered_display_name(guild, gid, new_uid)) or get_registered_display_name(guild, gid, new_uid)
            birth_lines.append(
                f"**{discord.utils.escape_markdown(str(left))} VS {discord.utils.escape_markdown(str(right))}**\n"
                f"맞대결 **{summary['games']}전 {summary['wins']}승 {summary['losses']}패** · 라이벌 점수 **{new_score:.1f}/100**"
            )
        return birth_lines
    def get_directed_rival_match_entries(gid, blue_ids, red_ids):
        blue_set = {str(uid) for uid in blue_ids}
        red_set = {str(uid) for uid in red_ids}
        entries = []
        for uid in list(blue_set | red_set):
            team = "blue" if uid in blue_set else "red"
            opponent_team = red_set if team == "blue" else blue_set
            rival_uid = get_custom_rival_uid(gid, uid)
            if rival_uid and rival_uid in opponent_team:
                entries.append({
                    "uid": uid,
                    "rival_uid": rival_uid,
                    "team": team,
                    "rival_team": "red" if team == "blue" else "blue",
                })
        entries.sort(key=lambda item: (item["team"], item["uid"], item["rival_uid"]))
        return entries
    def get_rival_head_to_head_summary(gid, uid, rival_uid):
        uid = str(uid)
        rival_uid = str(rival_uid)
        summary = {
            "games": 0,
            "wins": 0,
            "losses": 0,
            "latest": None,
        }

        for record in get_match_history(gid):
            if record.get("cancelled"):
                continue

            players = record.get("players", []) or []
            player = next((p for p in players if str(p.get("user_id")) == uid), None)
            rival = next((p for p in players if str(p.get("user_id")) == rival_uid), None)
            if not player or not rival:
                continue
            if player.get("team") == rival.get("team"):
                continue

            result = player.get("result")
            if result not in ("win", "loss"):
                continue

            summary["games"] += 1
            if result == "win":
                summary["wins"] += 1
            else:
                summary["losses"] += 1

            played_at = parse_history_time(record)
            latest = summary.get("latest")
            if played_at and (not latest or played_at > latest["time"]):
                summary["latest"] = {
                    "time": played_at,
                    "winner_uid": uid if result == "win" else rival_uid,
                    "mode": record.get("mode", "classic"),
                }

        return summary
    def format_rival_matchup_lines(guild, gid, entries):
        if not entries:
            return []
        used = set()
        lines = []
        entry_keys = {(item["uid"], item["rival_uid"]) for item in entries}
        for item in entries:
            uid = item["uid"]
            rival_uid = item["rival_uid"]
            if (uid, rival_uid) in used:
                continue
            if (rival_uid, uid) in entry_keys:
                used.add((uid, rival_uid))
                used.add((rival_uid, uid))
                uid_label = get_member_label(guild, gid, uid)
                rival_label = get_member_label(guild, gid, rival_uid)
                summary = get_rival_head_to_head_summary(gid, uid, rival_uid)
                if summary["games"] > 0:
                    latest = summary.get("latest")
                    latest_text = "최근 맞대결 기록 없음"
                    if latest:
                        latest_text = f"최근 승자: {get_member_label(guild, gid, latest['winner_uid'])} · {latest['time'].strftime('%Y-%m-%d')}"
                    lines.append(
                        f"{uid_label} ↔ {rival_label}\n"
                        f"현재 전적: {uid_label} 기준 **{summary['games']}전 {summary['wins']}승 {summary['losses']}패** · {latest_text}"
                    )
                else:
                    lines.append(f"{uid_label} ↔ {rival_label}\n현재 전적: **첫 맞대결**")
        return lines
    def format_head_to_head_record_line(guild, gid, uid, rival_uid):
        summary = get_rival_head_to_head_summary(gid, uid, rival_uid)
        if summary["games"] <= 0:
            return "상대전적 **첫 맞대결 예정**"

        latest = summary.get("latest")
        latest_text = ""
        if latest:
            latest_text = f"\n최근 승자: {get_member_label(guild, gid, latest['winner_uid'])} · {latest['time'].strftime('%Y-%m-%d')}"

        return (
            f"상대전적 **{summary['games']}전 {summary['wins']}승 {summary['losses']}패** "
            f"· 승률 **{calc_win_rate(summary):.1f}%**"
            f"{latest_text}"
        )
    def get_most_lane_rival_summary(gid, target_uid):
        target_uid = str(target_uid)
        lane_stats = defaultdict(lambda: {
            "games": 0,
            "wins": 0,
            "losses": 0,
            "roles": defaultdict(int),
        })

        for record in get_match_history(gid):
            if record.get("cancelled"):
                continue
            if record.get("mode") == NOBAN_MODE_KEY:
                continue

            players = record.get("players", []) or []
            target_player = next((p for p in players if str(p.get("user_id")) == target_uid), None)
            if not target_player:
                continue

            target_team = target_player.get("team")
            target_role = target_player.get("role")
            target_result = target_player.get("result")
            if target_role not in ROLES or target_result not in ("win", "loss"):
                continue

            for player in players:
                other_uid = str(player.get("user_id"))
                if other_uid == target_uid:
                    continue
                if player.get("team") == target_team:
                    continue
                if player.get("role") != target_role:
                    continue

                stats = lane_stats[other_uid]
                stats["games"] += 1
                stats["roles"][target_role] += 1
                if target_result == "win":
                    stats["wins"] += 1
                else:
                    stats["losses"] += 1

        if not lane_stats:
            return None

        uid, stats = max(
            lane_stats.items(),
            key=lambda item: (
                item[1]["games"],
                max(item[1]["roles"].values()) if item[1]["roles"] else 0,
                item[1]["wins"],
                calc_win_rate(item[1]),
            )
        )
        return {"uid": uid, **stats}
    def format_most_lane_rival_line(guild, gid, summary):
        if not summary:
            return "맞라인 기록이 아직 없습니다."

        games = int(summary.get("games", 0) or 0)
        wins = int(summary.get("wins", 0) or 0)
        losses = int(summary.get("losses", 0) or 0)
        role_counts = summary.get("roles", {}) or {}
        role, role_games = max(role_counts.items(), key=lambda item: item[1])
        lane_text = f"{role} {role_games}회" if role_games == games else f"{role} {role_games}회 등 총 {games}회"
        return f"{get_member_label(guild, gid, summary['uid'])}\n{lane_text} · **{wins}승 {losses}패**"
    def snapshot_rival_stats(gid, uids):
        snapshots = {}
        for uid in uids:
            raw_info = bot.user_data.get(gid, {}).get(str(uid))
            if not isinstance(raw_info, dict):
                continue
            stats = ensure_user_format(raw_info).get("rival_stats", {})
            snapshots[str(uid)] = {
                "games": int(stats.get("games", 0) or 0),
                "wins": int(stats.get("wins", 0) or 0),
                "losses": int(stats.get("losses", 0) or 0),
            }
        return snapshots
    def restore_rival_stats(gid, snapshots):
        for uid, stats in (snapshots or {}).items():
            if str(uid) not in bot.user_data.get(gid, {}):
                continue
            user_info = ensure_user_format(bot.user_data[gid][str(uid)])
            user_info["rival_stats"] = {
                "games": int(stats.get("games", 0) or 0),
                "wins": int(stats.get("wins", 0) or 0),
                "losses": int(stats.get("losses", 0) or 0),
            }
    async def apply_rival_match_results(interaction, gid, blue_ids, red_ids, winner_ids):
        entries = get_directed_rival_match_entries(gid, blue_ids, red_ids)
        if not entries:
            return [], []

        winner_set = {str(uid) for uid in winner_ids}
        lines = []
        changed_uids = set()
        for item in entries:
            uid = item["uid"]
            rival_uid = item["rival_uid"]
            user_info = ensure_user_format(bot.user_data[gid][uid])
            stats = user_info["rival_stats"]
            stats["games"] = int(stats.get("games", 0) or 0) + 1
            is_win = uid in winner_set
            if is_win:
                stats["wins"] = int(stats.get("wins", 0) or 0) + 1
            else:
                stats["losses"] = int(stats.get("losses", 0) or 0) + 1

            changed_uids.add(uid)
            result_text = "승리" if is_win else "패배"
            lines.append(
                f"{get_member_label(interaction.guild, gid, uid)} → {get_member_label(interaction.guild, gid, rival_uid)} "
                f"`{result_text}` · {stats['games']}전 {stats['wins']}승 {stats['losses']}패"
            )

        title_changed = False
        changed_uid_list = sorted(changed_uids)
        winning_uids = []
        fate_match_uids = []
        even_10_uids = []
        regular_title_uids = []

        def owns_rival_title(uid, title):
            raw_info = bot.user_data.get(gid, {}).get(str(uid), {})
            if not isinstance(raw_info, dict):
                return False
            titles = raw_info.get("titles", {})
            return isinstance(titles, dict) and title in titles.get("owned", [])

        def rival_title_has_owner(title):
            return any(owns_rival_title(uid, title) for uid, _ in iter_user_records(bot.user_data.get(gid, {})))

        async def grant_unowned_first_rival_title(uids, key):
            title = FIRST_TITLE_DEFS[key]["title"]
            # 과거 보유 기록 자체를 서버 최초 달성으로 인정하며 claim/획득 시각을 새로 쓰지 않는다.
            if rival_title_has_owner(title):
                return False
            eligible = [uid for uid in uids if not owns_rival_title(uid, title)]
            return await grant_first_team_title(interaction, gid, eligible, key) if eligible else False

        for uid in changed_uid_list:
            user_info = ensure_user_format(bot.user_data[gid][uid])
            stats = user_info["rival_stats"]
            games = int(stats.get("games", 0) or 0)
            wins = int(stats.get("wins", 0) or 0)
            losses = int(stats.get("losses", 0) or 0)
            if uid in winner_set and wins >= RIVAL_NAMED_WIN_WINS:
                winning_uids.append(uid)
            if games == RIVAL_FATE_MATCH_GAMES:
                fate_match_uids.append(uid)
            rival_title = GENERAL_TITLE_DEFS["rival_matches_7"]
            if games >= RIVAL_TITLE_MATCHES and not owns_rival_title(uid, rival_title):
                regular_title_uids.append(uid)
            if games == 10 and wins == 5 and losses == 5:
                even_10_uids.append(uid)

        first_title_granted = False
        if fate_match_uids:
            first_title_granted = await grant_unowned_first_rival_title(sorted(fate_match_uids), "first_rival_match")
        if not first_title_granted and even_10_uids:
            first_title_granted = await grant_unowned_first_rival_title(sorted(even_10_uids), "first_rival_10_even")
        if not first_title_granted and winning_uids:
            first_title_granted = await grant_unowned_first_rival_title(sorted(winning_uids), "first_rival_win")
        title_changed = first_title_granted or title_changed

        # 한 라이벌전에서 서로 다른 칭호가 연달아 지급되지 않도록 일반 누적 칭호는 다음 경기로 미룬다.
        if not first_title_granted:
            for uid in regular_title_uids:
                title_changed = await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["rival_matches_7"]) or title_changed

        return lines, entries
    async def rival_nickname_autocomplete(interaction: discord.Interaction, current: str):
        gid = str(interaction.guild_id)
        current_key = normalize_rival_search_text(current)
        requester_uid = str(interaction.user.id)
        choices = []
        seen_values = set()

        for uid, data in iter_user_records(bot.user_data.get(gid, {})):
            if str(uid) == requester_uid:
                continue
            user_info = ensure_user_format(data)
            member = interaction.guild.get_member(int(uid)) if interaction.guild else None
            lol_name = str(user_info.get("lol_name") or "").strip()
            display_name = str(member.display_name if member else "").strip()
            candidate_names = [name for name in (lol_name, display_name, str(uid)) if name]
            searchable = " ".join(candidate_names)
            if current_key and current_key not in normalize_rival_search_text(searchable):
                continue

            value = lol_name or display_name or str(uid)
            if value in seen_values:
                continue
            seen_values.add(value)
            shown_name = lol_name or display_name or f"UID {uid}"
            if display_name and display_name != shown_name:
                shown_name = f"{shown_name} · {display_name}"
            choices.append(app_commands.Choice(name=shown_name[:100], value=value[:100]))
            if len(choices) >= 25:
                break

        return choices
    def get_member_display_name(guild, gid, uid):
        member = guild.get_member(int(uid)) if guild else None
        if member:
            return member.display_name
        return get_saved_lol_name(gid, uid, f"탈퇴한 소환사({uid})")
    def get_registered_display_name(guild, gid, uid):
        member = guild.get_member(int(uid)) if guild else None
        fallback = member.display_name if member else f"탈퇴한 소환사({uid})"
        return get_saved_lol_name(gid, uid, fallback)
    def is_current_guild_member(guild, uid):
        """Public aggregates show only users still present in the Discord guild."""
        if guild is None:
            return True
        getter = getattr(guild, "get_member", None)
        if not callable(getter):
            return True
        try:
            return getter(int(uid)) is not None
        except (TypeError, ValueError):
            return False
    def iter_public_user_records(guild, gid):
        for uid, data in iter_user_records(bot.user_data.get(gid, {})):
            if is_current_guild_member(guild, uid):
                yield uid, data
    def get_record_role_placement_status(gid, user_info, role, played_games):
        if is_provisional_mmr_active(user_info, role):
            state = get_provisional_role_state(user_info, role, create=False) or {}
            target = int(get_provisional_mmr_config(gid)["games"])
            games = min(int(state.get("games", 0) or 0), target)
            return f"🟡 임시배치 {games}/{target}"
        if not is_role_mmr_assigned(user_info, role):
            return "⚪ 미배치"
        if int(played_games) < int(get_match_frequency_config(gid)["placement_games"]):
            return "🐣"
        return ""
    def get_ranking_entries(gid, line=None, limit=10, guild=None):
        if gid not in bot.user_data:
            return []

        entries = []
        for uid, data in iter_public_user_records(guild, gid):
            data = ensure_user_format(data)
            score = data['mmr'].get(line, 0) if line else get_avg_mmr(data['mmr'])
            if score > 0:
                entries.append((uid, score))

        entries.sort(key=lambda item: item[1], reverse=True)
        return entries[:limit]
    def build_ranking_embed(guild, gid, line=None):
        entries = get_ranking_entries(gid, line=line, limit=10, guild=guild)
        title = f"🏆 {line} 라인 랭킹 TOP 10" if line else "🏆 종합 MMR 랭킹 TOP 10"

        if not entries:
            description = "아직 표시할 랭킹 데이터가 없습니다."
        else:
            rows = []
            for rank, (uid, score) in enumerate(entries, 1):
                tier_name = get_tier_name(score)
                tier_emoji = get_tier_emoji(tier_name, guild, gid)
                name = get_registered_display_name(guild, gid, uid)
                rows.append(f"**{rank}위** | {tier_emoji} **{get_public_mmr_rank(score)}** | `{name}`")
            description = "\n".join(rows)

        embed = discord.Embed(title=title, description=description, color=0xFFD700)
        return embed

    EVENT_LEADERBOARDS_KEY = "_event_leaderboards"
    EVENT_METRIC_LABELS = {"games": "판수", "winrate": "승률", "mvp": "MVP"}
    EVENT_METRIC_CHOICES = [
        app_commands.Choice(name="판수", value="games"),
        app_commands.Choice(name="승률", value="winrate"),
        app_commands.Choice(name="MVP", value="mvp"),
    ]

    def get_event_leaderboards(gid):
        guild_data = bot.user_data.setdefault(str(gid), {})
        events = guild_data.setdefault(EVENT_LEADERBOARDS_KEY, {})
        if not isinstance(events, dict):
            events = {}
            guild_data[EVENT_LEADERBOARDS_KEY] = events
        return events

    def parse_event_date(value):
        return parse_date_option(value, default_year=now_kst().year)

    def get_event_ranking_rows(guild, gid, event):
        try:
            start_time = datetime.strptime(str(event.get("start_date")), "%Y-%m-%d")
            end_time = datetime.strptime(str(event.get("end_date")), "%Y-%m-%d") + timedelta(days=1)
        except (TypeError, ValueError):
            return []

        guild_data = bot.user_data.setdefault(str(gid), {})
        stats = defaultdict(lambda: {"games": 0, "wins": 0, "losses": 0, "mvp": 0})
        for record in get_valid_match_history(str(gid)):
            record_time = parse_history_time(record)
            if not record_time or not (start_time <= record_time < end_time):
                continue

            seen_uids = set()
            for player in record.get("players", []) or []:
                uid = str(player.get("user_id") or "").strip()
                if not uid or uid == "None" or uid in seen_uids or not is_current_guild_member(guild, uid):
                    continue
                seen_uids.add(uid)
                row = stats[uid]
                row["games"] += 1
                result = str(player.get("result") or "").strip().lower()
                if result == "win":
                    row["wins"] += 1
                elif result == "loss":
                    row["losses"] += 1

            match_id = record.get("id")
            if not match_id:
                continue
            try:
                award = (match_stats.score_match_awards(guild_data, str(match_id)) or {}).get("mvp") or {}
            except Exception:
                logger.exception("이벤트 MVP 집계 실패: %s", match_id)
                continue
            uid = str(award.get("user_id") or "").strip()
            if uid and uid != "None" and is_current_guild_member(guild, uid):
                stats[uid]["mvp"] += 1

        metric = str(event.get("metric") or "games")
        rows = []
        for uid, row in stats.items():
            games = int(row["games"] or 0)
            wins = int(row["wins"] or 0)
            losses = int(row["losses"] or 0)
            winrate = wins / games * 100 if games else 0.0
            rows.append({
                "uid": str(uid),
                "games": games,
                "wins": wins,
                "losses": losses,
                "winrate": winrate,
                "mvp": int(row["mvp"] or 0),
            })
        if metric == "winrate":
            rows.sort(key=lambda row: (row["winrate"], row["games"], row["wins"], row["uid"]), reverse=True)
        elif metric == "mvp":
            rows.sort(key=lambda row: (row["mvp"], row["games"], row["wins"], row["uid"]), reverse=True)
        else:
            rows.sort(key=lambda row: (row["games"], row["wins"], row["winrate"], row["uid"]), reverse=True)
        return rows

    def build_event_leaderboard_embed(guild, gid, event):
        metric = str(event.get("metric") or "games")
        rows = get_event_ranking_rows(guild, gid, event)[:10]
        lines = []
        for rank, row in enumerate(rows, 1):
            name = discord.utils.escape_markdown(get_registered_display_name(guild, gid, row["uid"]))
            if metric == "winrate":
                score_text = f"승률 **{row['winrate']:.1f}%**"
            elif metric == "mvp":
                score_text = f"MVP **{row['mvp']}회**"
            else:
                score_text = f"판수 **{row['games']}판**"
            lines.append(
                f"**{rank}위** `{name}` · {score_text} · {row['wins']}승 {row['losses']}패"
            )

        start_label = str(event.get("start_date") or "?").replace("-", ".")
        end_label = str(event.get("end_date") or "?").replace("-", ".")
        embed = discord.Embed(
            title=str(event.get("name") or "이벤트"),
            description=f"**이벤트 기간**\n{start_label} ~ {end_label}",
            color=0xF1C40F,
        )
        embed.add_field(
            name="랭킹",
            value="\n".join(lines) if lines else "해당 기간에 집계할 기록이 없습니다.",
            inline=False,
        )
        sponsor = str(event.get("sponsor") or "").strip()
        if sponsor:
            embed.add_field(name="🎁 후원", value=sponsor[:1024], inline=False)
        return embed

    async def update_event_leaderboards(guild, gid=None):
        gid = str(gid or guild.id)
        today = now_kst().date()
        changed = False
        for event in get_event_leaderboards(gid).values():
            try:
                start_date = datetime.strptime(str(event.get("start_date")), "%Y-%m-%d").date()
                end_date = datetime.strptime(str(event.get("end_date")), "%Y-%m-%d").date()
            except (TypeError, ValueError):
                continue
            if not start_date <= today <= end_date:
                continue
            channel_id = str(event.get("channel_id") or "")
            if not channel_id.isdigit():
                continue
            channel = guild.get_channel(int(channel_id))
            if not channel:
                continue
            embed = build_event_leaderboard_embed(guild, gid, event)
            try:
                message = await channel.fetch_message(int(event.get("message_id")))
                await edit_message_if_changed(message, embed=embed)
            except (discord.NotFound, TypeError, ValueError):
                try:
                    message = await channel.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    continue
                event["message_id"] = str(message.id)
                changed = True
            except (discord.Forbidden, discord.HTTPException):
                continue
        if changed:
            bot.save_lucid_data(gid)

    @bot.tree.command(name="이벤트생성", description="기간과 기준을 정해 이벤트 랭킹을 생성합니다.")
    @app_commands.describe(
        이름="이벤트 이름입니다.",
        시작일="집계 시작일입니다. YYYY-MM-DD 또는 M/D 형식입니다.",
        종료일="집계 종료일입니다. YYYY-MM-DD 또는 M/D 형식이며 해당 날짜를 포함합니다.",
        기준="판수, 승률, MVP 중 랭킹 기준입니다.",
        후원="선택 사항인 후원/상품 안내입니다.",
    )
    @app_commands.choices(기준=EVENT_METRIC_CHOICES)
    async def create_event_leaderboard(
        interaction: discord.Interaction,
        이름: str,
        시작일: str,
        종료일: str,
        기준: app_commands.Choice[str],
        후원: str = "",
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 내전 관리자만 이벤트를 생성할 수 있습니다.", ephemeral=True)
        event_name = str(이름 or "").strip()
        if not event_name or len(event_name) > 80:
            return await interaction.response.send_message("⚠️ 이벤트 이름은 1~80자로 입력해주세요.", ephemeral=True)
        start_date = parse_event_date(시작일)
        end_date = parse_event_date(종료일)
        if not start_date or not end_date:
            return await interaction.response.send_message("⚠️ 날짜는 YYYY-MM-DD 또는 M/D 형식으로 입력해주세요.", ephemeral=True)
        if start_date > end_date:
            return await interaction.response.send_message("⚠️ 시작일은 종료일보다 늦을 수 없습니다.", ephemeral=True)

        metric = 기준.value if 기준 else "games"
        events = get_event_leaderboards(str(interaction.guild_id))
        existing_key = next((key for key in events if str(key).casefold() == event_name.casefold()), None)
        key = existing_key or event_name
        events[key] = {
            "name": event_name,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "metric": metric,
            "sponsor": str(후원 or "").strip()[:500],
            "created_by": str(interaction.user.id),
            "created_at": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
        }
        bot.save_lucid_data(str(interaction.guild_id))
        embed = build_event_leaderboard_embed(interaction.guild, str(interaction.guild_id), events[key])
        await interaction.response.send_message(embed=embed)
        try:
            message = await interaction.original_response()
            events[key]["channel_id"] = str(message.channel.id)
            events[key]["message_id"] = str(message.id)
            bot.save_lucid_data(str(interaction.guild_id))
        except discord.HTTPException:
            pass

    @bot.tree.command(name="이벤트랭킹", description="저장된 이벤트의 현재 랭킹을 확인합니다.")
    @app_commands.describe(이름="조회할 이벤트 이름입니다.")
    async def event_leaderboard(interaction: discord.Interaction, 이름: str):
        event_name = str(이름 or "").strip()
        events = get_event_leaderboards(str(interaction.guild_id))
        key = next((key for key in events if str(key).casefold() == event_name.casefold()), None)
        if key is None:
            return await interaction.response.send_message("⚠️ 해당 이벤트를 찾을 수 없습니다.", ephemeral=True)
        await interaction.response.send_message(
            embed=build_event_leaderboard_embed(interaction.guild, str(interaction.guild_id), events[key])
        )
        try:
            message = await interaction.original_response()
            events[key]["channel_id"] = str(message.channel.id)
            events[key]["message_id"] = str(message.id)
            bot.save_lucid_data(str(interaction.guild_id))
        except discord.HTTPException:
            pass

    @bot.tree.command(name="이벤트삭제", description="저장된 이벤트와 연결된 후원 목록을 삭제합니다.")
    @app_commands.describe(이름="삭제할 이벤트 이름입니다.")
    async def delete_event_leaderboard(interaction: discord.Interaction, 이름: str):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 내전 관리자만 이벤트를 삭제할 수 있습니다.", ephemeral=True)
        gid = str(interaction.guild_id)
        events = get_event_leaderboards(gid)
        event_name = str(이름 or "").strip()
        key = next((key for key in events if str(key).casefold() == event_name.casefold()), None)
        if key is None:
            return await interaction.response.send_message("⚠️ 해당 이벤트를 찾을 수 없습니다.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        event = events.pop(key)
        delete_sponsor_sessions_for_party(gid, f"event:{key}")
        bot.save_lucid_data(gid)
        channel_id = str(event.get("channel_id") or "")
        message_id = str(event.get("message_id") or "")
        channel = interaction.guild.get_channel(int(channel_id)) if channel_id.isdigit() else None
        if channel and message_id.isdigit():
            try:
                message = await channel.fetch_message(int(message_id))
                await message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        await refresh_event_sponsor_panel(interaction.guild, gid)
        await interaction.followup.send(f"✅ **{discord.utils.escape_markdown(str(event.get('name') or key))}** 이벤트를 삭제했습니다.", ephemeral=True)

    async def update_ranking_board(guild, gid=None):
        gid = gid or str(guild.id)
        board = bot.user_data.get(gid, {}).get(RANKING_BOARD_KEY)
        if not board:
            return

        channel = guild.get_channel(int(board.get('channel_id', 0)))
        if not channel:
            return

        messages = board.setdefault('messages', {})
        targets = [("overall", None)] + [(role, role) for role in ROLES]
        changed = False

        # Discord edits do not move messages. If a missing board was recreated
        # later, remap the six existing snowflakes by creation order so refresh
        # repairs the visual order without sending another message.
        try:
            ordered_ids = sorted(int(messages.get(key)) for key, _line in targets)
        except (TypeError, ValueError):
            ordered_ids = []
        if len(ordered_ids) == len(targets) and len(set(ordered_ids)) == len(targets):
            normalized = {
                key: str(message_id)
                for (key, _line), message_id in zip(targets, ordered_ids)
            }
            if any(str(messages.get(key) or "") != message_id for key, message_id in normalized.items()):
                messages.update(normalized)
                changed = True

        kept_message_ids = {str(message_id) for message_id in messages.values() if message_id}
        try:
            async for message in channel.history(limit=100):
                if getattr(getattr(message, "author", None), "id", None) != getattr(bot.user, "id", None):
                    continue
                if str(getattr(message, "id", "")) in kept_message_ids:
                    continue
                if not message_has_any_embed_title(message, ("랭킹 TOP 10", "종합 MMR 랭킹", "라인 랭킹")):
                    continue
                try:
                    await message.delete()
                    await asyncio.sleep(0.15)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
        except (discord.Forbidden, discord.HTTPException):
            pass
        for key, line in targets:
            embed = build_ranking_embed(guild, gid, line=line)
            message_id = messages.get(key)
            try:
                if message_id:
                    message = await channel.fetch_message(int(message_id))
                    await edit_message_if_changed(message, embed=embed)
                else:
                    message = await channel.send(embed=embed)
                    messages[key] = str(message.id)
                    changed = True
            except discord.NotFound:
                try:
                    message = await channel.send(embed=embed)
                    messages[key] = str(message.id)
                    changed = True
                except discord.HTTPException:
                    continue
            except (discord.Forbidden, discord.HTTPException) as exc:
                logger.warning(
                    "랭킹보드 기존 메시지 갱신 실패(재생성 안 함): guild=%s key=%s message_id=%s error=%s",
                    gid,
                    key,
                    message_id,
                    exc,
                )

        if changed:
            bot.save_lucid_data(gid)
    def get_weekly_mvp_period(now=None):
        """Return the current Sunday-Saturday MVP ranking period in KST."""
        now = now or get_kst_now()
        # Python weekday(): Mon=0 ... Sun=6
        days_since_sunday = (now.weekday() + 1) % 7
        week_start = (now - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)
        week_no = ((week_start.day - 1) // 7) + 1
        label = f"{week_start.month}월 {week_no}주차"
        return week_start, week_end, label
    def _weekly_title_state(gid):
        state = bot.user_data.setdefault(gid, {}).setdefault("_weekly_mvp_title_state", {})
        if not isinstance(state, dict):
            state = {}
            bot.user_data.setdefault(gid, {})["_weekly_mvp_title_state"] = state
        state.setdefault("finalized", {})
        state.setdefault("last_winner_uid", None)
        state.setdefault("winner_streak", 0)
        return state
    def finalize_weekly_mvp_titles(guild, gid, now=None):
        """Finalize the previous Sunday-Saturday week once and award S2 weekly titles."""
        current_start, _current_end, _label = get_weekly_mvp_period(now)
        prev_start = current_start - timedelta(days=7)
        prev_end = current_start
        prev_week_no = ((prev_start.day - 1) // 7) + 1
        prev_label = f"{prev_start.month}월 {prev_week_no}주차"
        key = prev_start.strftime("%Y-%m-%d")
        state = _weekly_title_state(gid)
        if key in state["finalized"]:
            return False

        rows = get_award_point_rows(gid, start_time=prev_start, end_time=prev_end, guild=guild)
        winner_uid = str(rows[0][0]) if rows and int(rows[0][1] or 0) > 0 else None
        state["finalized"][key] = winner_uid or ""
        if not winner_uid:
            state["last_winner_uid"] = None
            state["winner_streak"] = 0
            return True

        weekly_title = f"🏆 주간의 주인공 - {prev_label}"
        add_title_to_user(gid, winner_uid, weekly_title)
        get_title_system(gid).setdefault("custom_conditions", {})[weekly_title] = f"{prev_label} MVP 포인트 랭킹 1위로 주간 마감"

        if state.get("last_winner_uid") == winner_uid:
            state["winner_streak"] = int(state.get("winner_streak", 0) or 0) + 1
        else:
            state["winner_streak"] = 1
        state["last_winner_uid"] = winner_uid
        if state["winner_streak"] >= 2:
            add_title_to_user(gid, winner_uid, GENERAL_TITLE_DEFS["weekly_mvp_twice"])
        return True
    def build_weekly_mvp_board_embed(guild, gid):
        week_start, week_end, week_label = get_weekly_mvp_period()
        rows = get_award_point_rows(gid, start_time=week_start, end_time=week_end, guild=guild)[:3]

        embed = discord.Embed(
            title=f"🏆 {week_label} MVP 랭킹",
            color=0xFFD700,
        )

        intro = "한 주간 내전에서 가장 뛰어난 활약을 한 플레이어\n`MVP +100pt` · `ACE +50pt`"
        if rows:
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            lines = []
            for rank, (uid, points, mvp_count, ace_count) in enumerate(rows, 1):
                name = compact_riot_name(get_registered_display_name(guild, gid, uid)) or get_registered_display_name(guild, gid, uid)
                safe_name = discord.utils.escape_markdown(str(name))
                lines.append(
                    f"{medals[rank]} **{safe_name}**\n"
                    f"　**{points}pt** · MVP **{mvp_count}회** · ACE **{ace_count}회**"
                )
            embed.description = intro + "\n\n" + "\n\n".join(lines)
        else:
            embed.description = intro + "\n\n이번 주 MVP/ACE 기록이 아직 없습니다."

        embed.set_footer(
            text=(
                f"MVP = 승리팀 최고 활약자 · ACE = 패배팀 최고 활약자 · "
                f"{week_start.strftime('%m.%d')} (일) ~ {(week_end - timedelta(days=1)).strftime('%m.%d')} (토)"
            )
        )
        return embed
    async def update_weekly_mvp_board(guild, gid=None):
        gid = gid or str(guild.id)
        if finalize_weekly_mvp_titles(guild, gid):
            bot.save_lucid_data(gid)
        board = bot.user_data.get(gid, {}).get(WEEKLY_MVP_BOARD_KEY)
        if not board:
            return
        try:
            channel = guild.get_channel(int(board.get("channel_id", 0)))
        except (TypeError, ValueError):
            channel = None
        if not channel:
            return

        embed = build_weekly_mvp_board_embed(guild, gid)
        message_id = board.get("message_id")
        changed = False
        try:
            if message_id:
                message = await channel.fetch_message(int(message_id))
                await edit_message_if_changed(message, embed=embed)
            else:
                message = await channel.send(embed=embed)
                board["message_id"] = str(message.id)
                changed = True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
            try:
                message = await channel.send(embed=embed)
                board["message_id"] = str(message.id)
                changed = True
            except discord.HTTPException:
                return
        if changed:
            bot.save_lucid_data(gid)
    def get_kst_now():
        return datetime.utcnow() + timedelta(hours=9)
    @tasks.loop(minutes=1)
    async def daily_ranking_board_refresh():
        now = get_kst_now()
        if now.hour != 10 or now.minute != 0:
            return

        today_key = now.strftime("%Y-%m-%d")
        for guild in bot.guilds:
            gid = str(guild.id)
            guild_data = bot.user_data.setdefault(gid, {})
            reign_refresh_state = guild_data.setdefault(WINRATE_REIGN_REFRESH_KEY, {})
            reign_changed = False
            if reign_refresh_state.get("last_date") != today_key:
                if record_winrate_reign_snapshot(gid, now, guild=guild):
                    reign_changed = True
                reign_refresh_state["last_date"] = today_key
                reign_refresh_state["last_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
                reign_changed = True
            if reign_changed:
                bot.save_lucid_data(gid)

            refresh_state = guild_data.setdefault(RANKING_REFRESH_KEY, {})
            if refresh_state.get("last_date") == today_key:
                continue
            try:
                if guild_data.get(RANKING_BOARD_KEY):
                    await update_ranking_board(guild, gid)
                if guild_data.get(WEEKLY_MVP_BOARD_KEY):
                    await update_weekly_mvp_board(guild, gid)
                refresh_state["last_date"] = today_key
                refresh_state["last_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
                bot.save_lucid_data(gid)
            except Exception as e:
                logger.warning(f"일일 랭킹보드/MVP 갱신 실패: guild={gid} ({e})")
    @tasks.loop(hours=1)
    async def hourly_ranking_board_refresh():
        for guild in bot.guilds:
            gid = str(guild.id)
            guild_data = bot.user_data.setdefault(gid, {})
            if not guild_data.get(RANKING_BOARD_KEY) and not guild_data.get(EVENT_LEADERBOARDS_KEY):
                continue
            try:
                if guild_data.get(RANKING_BOARD_KEY):
                    await update_ranking_board(guild, gid)
                if guild_data.get(EVENT_LEADERBOARDS_KEY):
                    await update_event_leaderboards(guild, gid)
            except Exception as e:
                logger.warning(f"시간별 랭킹보드 갱신 실패: guild={gid} ({e})")
            await asyncio.sleep(0.5)
    def find_registered_member_role(guild):
        if not guild:
            return None
        exact_role = discord.utils.get(getattr(guild, "roles", []) or [], name=REGISTERED_MEMBER_ROLE_NAME)
        if exact_role:
            return exact_role
        return next(
            (
                role for role in getattr(guild, "roles", []) or []
                if REGISTERED_MEMBER_ROLE_NAME in str(getattr(role, "name", "") or "")
                and not getattr(role, "managed", False)
                and role != getattr(guild, "default_role", None)
            ),
            None,
        )
    async def grant_registered_member_role(member):
        guild = getattr(member, "guild", None)
        role = find_registered_member_role(guild)
        if not role:
            return ""
        if role in getattr(member, "roles", []):
            return ""
        if not can_bot_manage_role(guild, role):
            return f"\n\n⚠️ `{role.name}` 역할을 지급하지 못했습니다. 봇 역할 순서/역할 관리 권한을 확인해주세요."
        try:
            await member.add_roles(role, reason="소환사등록 완료 자동 역할 지급")
            return f"\n\n✅ `{role.name}` 역할을 지급했습니다."
        except discord.Forbidden:
            return f"\n\n⚠️ `{role.name}` 역할을 지급하지 못했습니다. 봇 권한을 확인해주세요."
        except discord.HTTPException as exc:
            return f"\n\n⚠️ `{role.name}` 역할 지급 중 문제가 생겼습니다: `{str(exc)[:120]}`"
    def find_guest_roles(member):
        guild = getattr(member, "guild", None)
        default_role = getattr(guild, "default_role", None)
        roles = []
        for role in getattr(member, "roles", []) or []:
            role_name = str(getattr(role, "name", "") or "")
            if (
                GUEST_ROLE_NAME_KEYWORD in role_name
                and not getattr(role, "managed", False)
                and role != default_role
            ):
                roles.append(role)
        return roles
    async def remove_guest_roles_after_registration(member):
        guild = getattr(member, "guild", None)
        guest_roles = find_guest_roles(member)
        if not guest_roles:
            return ""

        removable = [role for role in guest_roles if can_bot_manage_role(guild, role)]
        blocked = [role for role in guest_roles if role not in removable]
        messages = []
        if removable:
            try:
                await member.remove_roles(*removable, reason="소환사등록 완료 게스트 역할 제거")
                role_names = ", ".join(f"`{role.name}`" for role in removable[:5])
                messages.append(f"✅ 게스트 역할을 제거했습니다: {role_names}")
            except discord.Forbidden:
                role_names = ", ".join(f"`{role.name}`" for role in removable[:5])
                messages.append(f"⚠️ 게스트 역할을 제거하지 못했습니다. 봇 권한을 확인해주세요: {role_names}")
            except discord.HTTPException as exc:
                messages.append(f"⚠️ 게스트 역할 제거 중 문제가 생겼습니다: `{str(exc)[:120]}`")
        if blocked:
            role_names = ", ".join(f"`{role.name}`" for role in blocked[:5])
            messages.append(f"⚠️ 게스트 역할을 제거하지 못했습니다. 봇 역할 순서/권한을 확인해주세요: {role_names}")
        return "\n\n" + "\n".join(messages) if messages else ""
    async def set_member_nickname(member, summoner_name):
        """Best-effort Discord nickname sync; Riot ID persistence is independent."""
        try:
            await member.edit(nick=summoner_name)
            return f"\n\n✨ 소환사 식별을 위해 서버 닉네임이 `{summoner_name}`(으)로 자동 변경되었습니다."
        except discord.Forbidden:
            return "\n\n⚠️ 서버 닉네임은 변경하지 못했지만 Riot ID 저장은 완료되었습니다."
        except Exception as exc:
            logger.debug("소환사 등록 닉네임 동기화 실패: member_id=%s", getattr(member, "id", None), exc_info=True)
            return "\n\n⚠️ 서버 닉네임은 변경하지 못했지만 Riot ID 저장은 완료되었습니다."
    async def register_summoner_profile(guild, member, summoner_name):
        gid = str(getattr(guild, "id", "") or "")
        uid = str(getattr(member, "id", "") or "")
        if not gid or not uid:
            return None, False, ""

        if gid not in bot.user_data: 
            bot.user_data[gid] = {}

        is_new_registration = uid not in bot.user_data[gid]
        if not is_new_registration:
            bot.user_data[gid][uid]['lol_name'] = summoner_name
            bot.user_data[gid][uid] = ensure_user_format(bot.user_data[gid][uid])
            embed_title = "🔄 소환사 정보 수정 완료"
            msg = f"**{member.display_name}** 님이 업데이트되었습니다.\n변동된 이름: **{summoner_name}**"
        else:
            bot.user_data[gid][uid] = {
                'lol_name': summoner_name,
                'mmr': {r: 0 for r in ROLES},
                'plays': {r: 0 for r in ROLES},
                'eval_scores': {r: [] for r in ROLES},
                'win': 0, 
                'loss': 0,
                'streak': 0 
            }
            bot.user_data[gid][uid] = ensure_user_format(bot.user_data[gid][uid])
            embed_title = "✅ 신규 소환사 시스템 등록 완료"
            msg = f"**{summoner_name}** 님, 시스템 등록을 환영합니다!\n초기 평균 MMR 점수는 **0점(아이언)**에서 시작합니다."

        bot.save_lucid_data(gid)
        try:
            await sync_registered_member_tier_role(guild, gid, uid)
        except Exception:
            logger.debug("소환사 등록 티어 역할 동기화 실패: guild_id=%s user_id=%s", gid, uid, exc_info=True)

        nick_msg = await set_member_nickname(member, summoner_name)

        role_msg = await grant_registered_member_role(member)
        guest_role_msg = await remove_guest_roles_after_registration(member)

        embed = discord.Embed(
            title=embed_title, 
            description=msg + nick_msg + role_msg + guest_role_msg,
            color=0x3498db
        )
        dm_status = ""
        if is_new_registration:
            dm_status = await send_member_welcome_dm(guild, member, summoner_name)
        return embed, is_new_registration, dm_status
    @bot.tree.command(name="소환사등록", description="Riot ID로 내전 시스템에 처음 등록합니다.")
    @app_commands.describe(소환사명="Riot ID 전체를 입력해주세요. 예시: Hide on bush#KR1")
    async def register_summoner(interaction: discord.Interaction, 소환사명: str):
        summoner_name = normalize_riot_id(str(소환사명 or "").strip())
        if not summoner_name:
            return await interaction.response.send_message(
                "⚠️ Riot ID는 `닉네임#태그` 형식으로 한 칸에 입력해주세요.\n"
                "예시: `Hide on bush#KR1`",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)
        embed, is_new_registration, dm_status = await register_summoner_profile(interaction.guild, interaction.user, summoner_name)
        await interaction.followup.send(embed=embed, ephemeral=True)
        if is_new_registration and dm_status:
            await interaction.followup.send(dm_status, ephemeral=True)
    async def register_alt_summoner(interaction: discord.Interaction, 유저: discord.Member, 부계정명: str):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)

        gid = str(interaction.guild_id)
        uid = str(유저.id)
        alt_name = 부계정명.strip()
        if not alt_name:
            return await interaction.response.send_message("⚠️ 등록할 부계정 Riot ID를 입력해주세요.", ephemeral=True)
        if "#" not in alt_name:
            return await interaction.response.send_message("⚠️ 부계정은 `닉네임#태그` 형식으로 입력해주세요.", ephemeral=True)
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 대상 유저는 먼저 `/소환사등록`이 필요합니다.", ephemeral=True)

        owner_uid, owner_name, is_alt = find_lol_account_owner(gid, alt_name, exclude_uid=uid)
        if owner_uid:
            owner_member = interaction.guild.get_member(int(owner_uid)) if interaction.guild else None
            owner_label = owner_member.mention if owner_member else f"UID {owner_uid}"
            kind = "부계정" if is_alt else "본계정"
            return await interaction.response.send_message(
                f"⚠️ `{owner_name}` 은(는) 이미 {owner_label} 님의 {kind}으로 등록되어 있습니다.",
                ephemeral=True
            )

        user_info = ensure_user_format(bot.user_data[gid][uid])
        if normalize_lol_account_key(user_info.get("lol_name")) == normalize_lol_account_key(alt_name):
            return await interaction.response.send_message("⚠️ 본계정 Riot ID와 같은 이름은 부계정으로 등록할 수 없습니다.", ephemeral=True)

        alt_names = user_info.setdefault("alt_lol_names", [])
        if any(normalize_lol_account_key(name) == normalize_lol_account_key(alt_name) for name in alt_names):
            return await interaction.response.send_message(f"⚠️ `{alt_name}` 은(는) 이미 해당 유저의 부계정으로 등록되어 있습니다.", ephemeral=True)

        alt_names.append(alt_name)
        bot.user_data[gid][uid] = ensure_user_format(user_info)
        bot.save_lucid_data(gid)

        alt_list = "\n".join(f"• `{name}`" for name in bot.user_data[gid][uid].get("alt_lol_names", [])) or "없음"
        embed = discord.Embed(
            title="✅ 부계정 등록 완료",
            description=(
                f"대상: {유저.mention}\n"
                f"부계정: `{alt_name}`\n\n"
                "이제 ROFL 상세스탯 저장 시 해당 계정도 같은 유저로 인식합니다."
            ),
            color=0x2ecc71
        )
        embed.add_field(name="등록된 부계정", value=alt_list, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    async def delete_alt_summoner(interaction: discord.Interaction, 유저: discord.Member, 부계정명: str):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)

        gid = str(interaction.guild_id)
        uid = str(유저.id)
        alt_name = 부계정명.strip()
        if not alt_name:
            return await interaction.response.send_message("⚠️ 삭제할 부계정 Riot ID를 입력해주세요.", ephemeral=True)
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 대상 유저는 등록된 소환사가 아닙니다.", ephemeral=True)

        user_info = ensure_user_format(bot.user_data[gid][uid])
        before = list(user_info.get("alt_lol_names", []))
        user_info["alt_lol_names"] = [
            name for name in before
            if normalize_lol_account_key(name) != normalize_lol_account_key(alt_name)
        ]
        if len(before) == len(user_info["alt_lol_names"]):
            return await interaction.response.send_message(f"⚠️ `{alt_name}` 은(는) 해당 유저의 부계정 목록에 없습니다.", ephemeral=True)

        bot.user_data[gid][uid] = user_info
        bot.save_lucid_data(gid)
        alt_list = "\n".join(f"• `{name}`" for name in user_info.get("alt_lol_names", [])) or "없음"
        embed = discord.Embed(
            title="🗑️ 부계정 삭제 완료",
            description=f"대상: {유저.mention}\n삭제: `{alt_name}`",
            color=0xe67e22
        )
        embed.add_field(name="남은 부계정", value=alt_list, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @bot.tree.command(name="전적", description="본인 또는 다른 유저의 전적과 라인별 MMR을 확인합니다.")
    async def record(interaction: discord.Interaction, 유저: discord.Member = None):
        t = 유저 or interaction.user
        gid = str(interaction.guild_id)
        
        if gid not in bot.user_data or str(t.id) not in bot.user_data[gid]:
            return await interaction.response.send_message(
                f"⚠️ **{t.display_name}** 님은 아직 등록되지 않은 소환사입니다. `/소환사등록`을 먼저 진행해 주세요.", 
                ephemeral=True
            )
            
        d = bot.user_data[gid][str(t.id)]
        d = ensure_user_format(d)
        
        avg_mmr = get_avg_mmr(d['mmr'])
        tier = get_tier_name(avg_mmr)
        
        total = d['win'] + d['loss']
        wr = (d['win'] / total * 100) if total > 0 else 0.0
        most_role, most_ratio = get_most_played_role(d['plays'])
        peak_role, peak_mmr = get_peak_role_mmr(d['mmr'])
        current_streak = format_streak_display(d.get('streak', 0))
        
        equipped_title = get_equipped_title(d)
        embed_tier = get_tier_name(peak_mmr) if peak_role else tier
        compact_lol_name = compact_riot_name(d.get('lol_name', t.display_name)) or d.get('lol_name', t.display_name)
        embed = discord.Embed(
            title=f"👤 {compact_lol_name} 님의 전적",
            color=TIER_DATA[embed_tier]['color']
        )
        if equipped_title:
            embed.description = f"칭호: {format_user_equipped_title(interaction.guild, gid, d, equipped_title)}"
        
        peak_value = "기록 없음"
        if peak_role:
            peak_value = format_match_role_score(peak_role, peak_mmr, interaction.guild, gid)
        embed.add_field(name="최고 라인", value=peak_value, inline=True)
        embed.add_field(name="평균 티어", value=f"{format_public_mmr(avg_mmr, interaction.guild, gid)}", inline=True)
        embed.add_field(name="내전 전체 전적", value=f"`{d['win']}승 {d['loss']}패` (승률: {wr:.1f}%)", inline=True)
        if most_role:
            most_value = f"{get_role_display_marker(most_role, interaction.guild)} {most_role} ({most_ratio:.1f}%)"
        else:
            most_value = "🎯 없음"
        embed.add_field(name="주 포지션", value=most_value, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="현재 흐름", value=f"{current_streak}", inline=True)
        
        role_lines = []
        display_role_stats = get_display_role_stats(gid, str(t.id), d)
        for r in ROLES:
            p_count = d['plays'].get(r, 0)
            p_status = get_record_role_placement_status(gid, d, r, p_count)
            status_suffix = f" · {p_status}" if p_status else ""
            role_stats = display_role_stats.get(r, {})
            role_wins = role_stats.get('win', 0)
            role_losses = role_stats.get('loss', 0)
            role_total = role_wins + role_losses
            if role_total <= 0:
                role_lines.append(
                    f"• {get_role_display_marker(r, interaction.guild)} {format_public_mmr_division_points(d['mmr'][r], interaction.guild, gid)}{status_suffix}"
                )
                continue

            role_wr = f"{(role_wins / role_total * 100):.1f}%" if role_total else "-"
            role_lines.append(
                f"• {get_role_display_marker(r, interaction.guild)} {format_public_mmr_division_points(d['mmr'][r], interaction.guild, gid)} · {role_total}전 · {role_wr}{status_suffix}"
            )

        if role_lines:
            embed.add_field(name="📊 포지션별 기록", value="\n" + "\n".join(role_lines), inline=False)

        noban_mmr = get_noban_mmr(d)
        noban_stats = d.get('noban_stats', {})
        noban_wins = int(noban_stats.get('win', 0) or 0)
        noban_losses = int(noban_stats.get('loss', 0) or 0)
        noban_total = noban_wins + noban_losses
        if noban_mmr > 0 or noban_total > 0:
            noban_wr = (noban_wins / noban_total * 100) if noban_total > 0 else 0.0
            noban_tier = get_tier_name(noban_mmr)
            embed.add_field(
                name="🚫 노밴 모드",
                value=(
                    f"MMR **{format_public_mmr(noban_mmr, interaction.guild, gid)}**\n"
                    f"`{noban_wins}승 {noban_losses}패` (승률: {noban_wr:.1f}%)"
                ),
                inline=False
            )

        arena_stats = d.get('event_stats', {}).get(EVENT_MODE_KEY, {'win': 0, 'loss': 0})
        arena_wins = safe_detail_int(arena_stats.get('win', 0))
        arena_losses = safe_detail_int(arena_stats.get('loss', 0))
        arena_total = arena_wins + arena_losses
        arena_wr = (arena_wins / arena_total * 100) if arena_total > 0 else 0.0
        aram_stats = d.get('event_stats', {}).get(ARAM_MODE_KEY, {'win': 0, 'loss': 0})
        aram_wins = safe_detail_int(aram_stats.get('win', 0))
        aram_losses = safe_detail_int(aram_stats.get('loss', 0))
        aram_total = aram_wins + aram_losses
        aram_wr = (aram_wins / aram_total * 100) if aram_total > 0 else 0.0
        event_record_lines = []
        if arena_total > 0:
            event_record_lines.append(f"{EVENT_MODE_NAME}: `{arena_wins}승 {arena_losses}패` (승률: {arena_wr:.1f}%)")
        if aram_total > 0:
            event_record_lines.append(f"{ARAM_MODE_NAME}: `{aram_wins}승 {aram_losses}패` (승률: {aram_wr:.1f}%)")
        aram_league_stats = d.get('aram_league_stats', {})
        aram_league_match_win = safe_detail_int(aram_league_stats.get('match_win', 0))
        aram_league_match_loss = safe_detail_int(aram_league_stats.get('match_loss', 0))
        aram_league_participations = safe_detail_int(aram_league_stats.get('participations', 0))
        aram_league_wins = safe_detail_int(aram_league_stats.get('wins', 0))
        if aram_league_match_win + aram_league_match_loss + aram_league_participations > 0:
            event_record_lines.append(
                f"{ARAM_LEAGUE_MODE_NAME}: `매치 {aram_league_match_win}승 {aram_league_match_loss}패` · 참가 {aram_league_participations}회 · 우승 {aram_league_wins}회"
            )
        if event_record_lines:
            embed.add_field(
                name="🏟️ 이벤트 모드 전적",
                value="\n".join(event_record_lines),
                inline=False
            )
        embed.set_footer(text=PROMO_FOOTER)

        await interaction.response.send_message(embed=embed)
    @bot.tree.command(name="상세전적", description="누적 상세 전적 요약 또는 라인별 상세 전적을 확인합니다.")
    @app_commands.choices(보기=[
        app_commands.Choice(name="전체", value="전체"),
        app_commands.Choice(name="탑", value="탑"),
        app_commands.Choice(name="정글", value="정글"),
        app_commands.Choice(name="미드", value="미드"),
        app_commands.Choice(name="원딜", value="원딜"),
        app_commands.Choice(name="서폿", value="서폿"),
    ])
    async def detailed_record(interaction: discord.Interaction, 보기: str = "", 유저: discord.Member = None):
        t = 유저 or interaction.user
        gid = str(interaction.guild_id)

        if gid not in bot.user_data or str(t.id) not in bot.user_data[gid]:
            return await interaction.response.send_message(
                f"⚠️ **{t.display_name}** 님은 아직 등록되지 않은 소환사입니다. `/소환사등록`을 먼저 진행해 주세요.",
                ephemeral=True
            )

        보기 = "" if 보기 == "전체" else 보기
        detail_view = normalize_record_detail_view(보기)
        role = detail_view[1] if detail_view and detail_view[0] == "role" else None
        if 보기 and not role:
            return await interaction.response.send_message(
                "⚠️ 상세전적 보기는 `탑`, `정글`, `미드`, `원딜`, `서폿` 중 하나로 입력해 주세요.",
                ephemeral=True
            )

        guild_data = bot.user_data.setdefault(gid, {})
        row = aggregate_detail_entries(guild_data, user_id=str(t.id), role=role)
        if not row:
            empty = f"📭 아직 `{role}` 라인 상세 전적이 없습니다." if role else "📭 아직 기록된 상세 전적이 없습니다."
            return await interaction.response.send_message(empty, ephemeral=True)

        champion_rows = aggregate_detail_entries(guild_data, user_id=str(t.id), role=role, group_key="champion")
        title = f"📊 {t.display_name} {role} 상세 전적" if role else f"📊 {t.display_name} 상세 전적"
        embed = build_detail_summary_embed(title, row, champion_rows, role=role, guild=interaction.guild)
        await interaction.response.send_message(embed=embed)
    @bot.tree.command(name="성장분석", description="최근 내전 기준 성장 흐름과 상세 지표 변화를 확인합니다.")
    async def growth_report(interaction: discord.Interaction, 유저: discord.Member = None):
        gid = str(interaction.guild_id)
        target = 유저 or interaction.user
        uid = str(target.id)

        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message(
                f"⚠️ **{target.display_name}** 님은 아직 등록되지 않은 소환사입니다.",
                ephemeral=True
            )

        user_info = ensure_user_format(bot.user_data[gid][uid])
        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)
        entries = []

        for record in records:
            for player in record.get('players', []):
                if str(player.get('user_id')) != uid:
                    continue
                if not all(k in player for k in ('role', 'result', 'delta', 'before_mmr', 'after_mmr')):
                    continue
                if not isinstance(player.get('delta'), int):
                    continue
                entries.append({
                    'time': parse_history_time(record),
                    'role': player.get('role', '?'),
                    'result': player.get('result', '?'),
                    'delta': player.get('delta', 0),
                    'before': player.get('before_mmr', 0),
                    'after': player.get('after_mmr', 0),
                })
                break
            if len(entries) >= 10:
                break

        if not entries:
            return await interaction.response.send_message(
                "📭 아직 성장 요약을 만들 만큼의 내전 기록이 없습니다.",
                ephemeral=True
            )

        wins = sum(1 for e in entries if e['result'] == 'win')
        losses = sum(1 for e in entries if e['result'] == 'loss')
        total_delta = sum(e['delta'] for e in entries)
        winrate = wins / len(entries) * 100

        role_summary = {}
        for role in ROLES:
            role_entries = [e for e in entries if e['role'] == role]
            if not role_entries:
                continue
            role_wins = sum(1 for e in role_entries if e['result'] == 'win')
            role_delta = sum(e['delta'] for e in role_entries)
            role_summary[role] = {
                'games': len(role_entries),
                'wins': role_wins,
                'losses': len(role_entries) - role_wins,
                'delta': role_delta,
            }

        role_lines = []
        for role in ROLES:
            stat = role_summary.get(role)
            if not stat:
                continue
            role_lines.append(
                f"**[{role}]** {stat['games']}전 {stat['wins']}승 {stat['losses']}패 · `{stat['delta']:+}점`"
            )

        best_role = max(role_summary.items(), key=lambda x: x[1]['delta'], default=None)
        worst_role = min(role_summary.items(), key=lambda x: x[1]['delta'], default=None)
        latest = entries[0]
        latest_icon = "승리" if latest['result'] == 'win' else "패배"
        latest_time = latest['time'].strftime("%m-%d %H:%M") if latest.get('time') else "기록 없음"

        peak_role, peak_mmr = get_peak_role_mmr(user_info['mmr'])
        embed_tier = get_tier_name(peak_mmr) if peak_role else get_tier_name(get_avg_mmr(user_info['mmr']))
        embed = discord.Embed(
            title=f"📈 {user_info.get('lol_name', target.display_name)} 님의 성장 요약",
            description="최근 일반 내전 10경기 기준으로 계산됩니다.",
            color=TIER_DATA[embed_tier]['color']
        )
        embed.add_field(
            name="최근 흐름",
            value=f"`{len(entries)}전 {wins}승 {losses}패` · 승률 **{winrate:.1f}%**\n총 변화 `{total_delta:+}점` · 현재 {format_streak_display(user_info.get('streak', 0))}",
            inline=False
        )
        embed.add_field(
            name="라인별 변화",
            value="\n".join(role_lines) if role_lines else "라인별 기록이 부족합니다.",
            inline=False
        )
        embed.add_field(
            name="가장 오른 라인",
            value=f"**{best_role[0]}** `{best_role[1]['delta']:+}점`" if best_role else "기록 없음",
            inline=True
        )
        embed.add_field(
            name="가장 흔들린 라인",
            value=f"**{worst_role[0]}** `{worst_role[1]['delta']:+}점`" if worst_role and worst_role[1]['delta'] < 0 else "최근 하락 라인 없음",
            inline=True
        )
        embed.add_field(
            name="최근 경기",
            value=f"{latest_time} · **{latest['role']}** · {latest_icon}\n`{latest['before']} → {latest['after']}` (`{latest['delta']:+}점`)",
            inline=False
        )
        detail_row = aggregate_detail_entries(bot.user_data.setdefault(gid, {}), user_id=uid)
        if detail_row:
            mvp_count = int(detail_row.get("mvp_count", 0) or 0)
            ace_count = int(detail_row.get("ace_count", 0) or 0)
            mvp_points = mvp_count * 100 + ace_count * 50
            embed.add_field(
                name="상세 지표",
                value=(
                    f"KDA **{detail_row.get('kda', 0):.1f}** · "
                    f"킬 관여율 **{detail_row.get('avg_kp', 0):.1f}%** · "
                    f"분당 피해량 **{detail_row.get('dpm', 0):.0f}**\n"
                    f"MVP **{mvp_count}회** · ACE **{ace_count}회** · MVP 포인트 **{mvp_points}P**"
                ),
                inline=False,
            )
        embed.set_footer(text=PROMO_FOOTER)
        await interaction.response.send_message(embed=embed)
    @bot.tree.command(name="티어그래프", description="MMR 변화 그래프를 확인합니다.")
    @app_commands.choices(라인=[app_commands.Choice(name=r, value=r) for r in ROLES])
    @app_commands.describe(
        유저="그래프를 확인할 소환사",
        라인="특정 라인만 보고 싶으면 선택하세요. 비우면 종합 평균 추이를 표시합니다.",
        경기수="최근 몇 경기를 볼지 선택합니다. 기본값은 50경기입니다."
    )
    async def tier_graph(
        interaction: discord.Interaction,
        유저: discord.Member = None,
        라인: app_commands.Choice[str] = None,
        경기수: app_commands.Range[int, 5, 200] = 50
    ):
        await interaction.response.defer(ephemeral=True)

        if not plt:
            return await interaction.followup.send(
                "⚠️ 그래프 기능에 필요한 `matplotlib` 패키지가 설치되어 있지 않습니다.",
                ephemeral=True
            )

        gid = str(interaction.guild_id)
        target = 유저 or interaction.user
        uid = str(target.id)

        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.followup.send(
                f"⚠️ **{target.display_name}** 님은 아직 등록되지 않은 소환사입니다.",
                ephemeral=True
            )

        line_name = 라인.value if 라인 else None
        entries = build_tier_graph_entries(gid, uid, line=line_name, limit=경기수)
        if not entries:
            scope = f"**[{line_name}]** 라인" if line_name else "종합"
            return await interaction.followup.send(
                f"📭 {scope} 그래프를 만들 경기 기록이 아직 없습니다.",
                ephemeral=True
            )

        file = make_tier_graph_file(target.display_name, entries, line=line_name)
        if not file:
            return await interaction.followup.send("⚠️ 그래프 이미지를 생성하지 못했습니다.", ephemeral=True)

        wins = sum(1 for entry in entries if entry.get("result") == "win")
        losses = sum(1 for entry in entries if entry.get("result") == "loss")
        start_score = entries[0]["score"]
        end_score = entries[-1]["score"]
        scope = f"{line_name} 라인" if line_name else "종합 평균"
        embed = discord.Embed(
            title=f"📈 {target.display_name} 님의 티어 그래프",
            description=f"기준: **{scope}** · X축: **경기 수**",
            color=0x2ecc71 if end_score >= start_score else 0xe74c3c
        )
        embed.add_field(name="표시 경기", value=f"{len(entries)}경기", inline=True)
        embed.add_field(name="승 / 패", value=f"{wins}승 {losses}패", inline=True)
        embed.add_field(name="MMR 변화", value=f"{start_score} → {end_score} ({end_score - start_score:+})", inline=True)
        embed.set_image(url="attachment://tier_graph.png")
        embed.set_footer(text="초록 점은 승리, 빨간 점은 패배입니다.")

        await interaction.followup.send(embed=embed, file=file)
    @bot.tree.command(name="랭킹", description="내전 랭킹을 종류별로 확인합니다.")
    @app_commands.describe(
        종류="조회할 랭킹 종류입니다.",
        페이지="조회할 페이지입니다. 1페이지는 1~10등, 2페이지는 11~20등입니다.",
        라인="MMR 랭킹에서 특정 라인의 순위를 조회하려면 선택하세요. 선택하지 않으면 평균 MMR 기준입니다."
    )
    @app_commands.choices(
        종류=[
            app_commands.Choice(name="MMR", value="mmr"),
            app_commands.Choice(name="판수", value="games"),
            app_commands.Choice(name="승률", value="winrate"),
            app_commands.Choice(name="연승", value="streak"),
            app_commands.Choice(name="수상", value="awards"),
        ],
        라인=[app_commands.Choice(name=r, value=r) for r in ROLES]
    )
    async def ranking(
        interaction: discord.Interaction,
        종류: app_commands.Choice[str] = None,
        라인: str = None,
        페이지: app_commands.Range[int, 1, 999] = 1
    ):
        rank_type = 종류.value if 종류 else "mmr"
        if rank_type == "games":
            return await games_ranking(interaction)
        if rank_type == "winrate":
            return await winrate_ranking(interaction)
        if rank_type == "streak":
            return await streak_ranking(interaction)
        if rank_type == "awards":
            return await detail_award_ranking(interaction, min(int(페이지 or 1), 50))

        gid = str(interaction.guild_id)
        
        if gid not in bot.user_data or not bot.user_data[gid]:
            return await interaction.response.send_message(
                "📊 서버 내에 축적된 소환사 데이터베이스가 존재하지 않습니다.", 
                ephemeral=True
            )

        active_users = {}
        for uid, data in iter_public_user_records(interaction.guild, gid):
            data = ensure_user_format(data)
            if 라인:
                score = data['mmr'].get(라인, 0)
            else:
                score = get_avg_mmr(data['mmr'])
                
            if score > 0: 
                active_users[uid] = score
        
        if not active_users:
            target_string = f"[{라인}] 포지션 활성화 점수를 보유한" if 라인 else "랭킹 시스템에 진입 가능한"
            return await interaction.response.send_message(
                f"📊 현재 {target_string} 소환사가 배치되지 않았습니다.", 
                ephemeral=True
            )

        sorted_users = sorted(active_users.items(), key=lambda x: x[1], reverse=True)
        total_pages = max(1, (len(sorted_users) + 9) // 10)
        
        if 페이지 > total_pages:
            return await interaction.response.send_message(
                f"📊 현재 랭킹은 {total_pages}페이지까지 있습니다. `페이지` 값을 {total_pages} 이하로 입력해 주세요.",
                ephemeral=True
            )

        start_index = (페이지 - 1) * 10
        page_users = sorted_users[start_index:start_index + 10]
        ranking_list = []
        
        for i, (uid, score) in enumerate(page_users, start_index + 1):
            tier_name = get_tier_name(score)
            tier_emoji = get_tier_emoji(tier_name, interaction.guild, gid)
            name = get_registered_display_name(interaction.guild, gid, uid)
            ranking_list.append(f"**{i}위** | {tier_emoji} `{name}` ➡️ **{get_public_mmr_rank(score)}**")

        title_text = f"🏆 내전 포지션 {get_role_display_marker(라인, interaction.guild)} 순위" if 라인 else "🏆 내전 MMR 리더보드"
        
        embed = discord.Embed(
            title=title_text, 
            description="\n".join(ranking_list), 
            color=0xFFD700
        )
        embed.set_footer(
            text=f"{페이지}/{total_pages}페이지 · {start_index + 1}~{start_index + len(page_users)}등 | {PROMO_FOOTER}"
        )
        await interaction.response.send_message(embed=embed)
    def get_hall_rank_icon(rank):
        return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"`{rank}위`")
    def format_hall_name_line(rank, name):
        return f"{get_hall_rank_icon(rank)} {name}"
    def format_hall_detail_line(*parts):
        return "└ " + " · ".join(str(part) for part in parts if str(part or "").strip())
    def get_hall_display_name(guild, gid, uid):
        return compact_riot_name(get_registered_display_name(guild, gid, uid))
    def get_hall_role_record(gid, uid, user_info, role):
        stats = get_display_role_stats(gid, uid, user_info).get(role, {})
        wins = int(stats.get("win", 0) or 0)
        losses = int(stats.get("loss", 0) or 0)
        games = int(user_info.get("plays", {}).get(role, 0) or 0)
        if wins + losses == games:
            return wins, losses
        inferred = infer_auto_role_record(gid, uid, user_info, role)
        return int(inferred.get("wins", 0) or 0), int(inferred.get("losses", 0) or 0)
    def build_hall_streak_embed(guild, gid):
        entries = []
        changed = False
        for uid, data in iter_public_user_records(guild, gid):
            user_info = ensure_user_format(data)
            before = int(user_info.setdefault("peak_records", {}).get("best_streak", 0) or 0)
            peak_records = update_peak_records(user_info)
            best_streak = int(peak_records.get("best_streak", 0) or 0)
            if best_streak != before:
                changed = True
            current_streak = max(0, int(user_info.get("streak", 0) or 0))
            if best_streak > 0:
                entries.append((uid, best_streak, current_streak))

        if changed:
            bot.save_lucid_data(gid)

        entries.sort(key=lambda item: (item[1], item[2]), reverse=True)
        if not entries:
            description = "아직 명예의 전당에 등록할 연승 기록이 없습니다."
        else:
            lines = []
            for rank, (uid, best_streak, current_streak) in enumerate(entries[:HALL_OF_FAME_TOP_LIMIT], 1):
                name = get_hall_display_name(guild, gid, uid)
                details = [f"최고 {best_streak}연승"]
                if current_streak >= best_streak:
                    details.append("기록 도전 중!")
                lines.append(f"{format_hall_name_line(rank, name)}\n{format_hall_detail_line(*details)}")
            description = "\n".join(lines)

        embed = discord.Embed(
            title="🏛️ 명예의 전당 · 최고 연승",
            description=description,
            color=0xf1c40f
        )
        embed.set_footer(text="일반 내전 승리 기록 기준 · 패배 시 현재 연승은 끊기지만 최고 기록은 보존됩니다.")
        return embed
    def build_hall_role_mmr_embed(guild, gid, role):
        entries = []
        for uid, data in iter_public_user_records(guild, gid):
            user_info = ensure_user_format(data)
            games = int(user_info.get("plays", {}).get(role, 0) or 0)
            score = int(user_info.get("mmr", {}).get(role, 0) or 0)
            if games < HALL_OF_FAME_MIN_ROLE_GAMES or score <= 0:
                continue
            wins, losses = get_hall_role_record(gid, uid, user_info, role)
            entries.append((uid, score, games, wins, losses))

        entries.sort(key=lambda item: (item[1], item[3], -item[4]), reverse=True)
        if not entries:
            description = f"아직 {role} 라인 5판 이상 기록자가 없습니다."
        else:
            lines = []
            for rank, (uid, score, games, wins, losses) in enumerate(entries[:HALL_OF_FAME_TOP_LIMIT], 1):
                tier_name = get_tier_name(score)
                tier_emoji = get_tier_emoji(tier_name, guild, gid)
                name = get_hall_display_name(guild, gid, uid)
                lines.append(f"{format_hall_name_line(rank, name)}\n{format_hall_detail_line(f'{tier_emoji} {get_public_mmr_rank(score)}', f'{games}판', f'{wins}승 {losses}패')}")
            description = "\n".join(lines)

        embed = discord.Embed(
            title=f"🏛️ 명예의 전당 · {get_role_display_marker(role, guild)} 최고 MMR",
            description=description,
            color=0x3498db
        )
        embed.set_footer(text=f"{role} 라인 {HALL_OF_FAME_MIN_ROLE_GAMES}판 이상 플레이 기록만 집계합니다.")
        return embed
    def get_best_role_growth_entry(gid, role, guild=None):
        best = None
        for uid, data in iter_public_user_records(guild, gid):
            user_info = ensure_user_format(data)
            games = int(user_info.get("plays", {}).get(role, 0) or 0)
            current_mmr = int(user_info.get("mmr", {}).get(role, 0) or 0)
            start_mmr = get_role_initial_mmr(user_info, role, 0)
            if games < HALL_OF_FAME_MIN_ROLE_GAMES or start_mmr <= 0 or current_mmr <= 0:
                continue
            growth = current_mmr - start_mmr
            if growth <= 0:
                continue
            wins, losses = get_hall_role_record(gid, uid, user_info, role)
            candidate = {
                "uid": uid,
                "role": role,
                "start": start_mmr,
                "current": current_mmr,
                "growth": growth,
                "games": games,
                "wins": wins,
                "losses": losses,
            }
            if best is None or (candidate["growth"], candidate["current"], candidate["wins"]) > (best["growth"], best["current"], best["wins"]):
                best = candidate
        return best
    def get_overall_growth_entries(gid, guild=None):
        entries = []
        for uid, data in iter_public_user_records(guild, gid):
            user_info = ensure_user_format(data)
            role_entries = []
            for role in ROLES:
                games = int(user_info.get("plays", {}).get(role, 0) or 0)
                current_mmr = int(user_info.get("mmr", {}).get(role, 0) or 0)
                start_mmr = get_role_initial_mmr(user_info, role, 0)
                if games < HALL_OF_FAME_MIN_ROLE_GAMES or start_mmr <= 0 or current_mmr <= 0:
                    continue
                role_entries.append((role, start_mmr, current_mmr, games))
            if not role_entries:
                continue

            start_avg = int(sum(item[1] for item in role_entries) / len(role_entries))
            current_avg = int(sum(item[2] for item in role_entries) / len(role_entries))
            growth = current_avg - start_avg
            if growth <= 0:
                continue

            total_wins = 0
            total_losses = 0
            total_games = 0
            for role, _start, _current, games in role_entries:
                wins, losses = get_hall_role_record(gid, uid, user_info, role)
                total_wins += wins
                total_losses += losses
                total_games += games

            entries.append({
                "uid": uid,
                "start": start_avg,
                "current": current_avg,
                "growth": growth,
                "games": total_games,
                "wins": total_wins,
                "losses": total_losses,
                "roles": len(role_entries),
            })
        entries.sort(key=lambda item: (item["growth"], item["current"], item["wins"]), reverse=True)
        return entries
    def get_best_overall_growth_entry(gid, guild=None):
        entries = get_overall_growth_entries(gid, guild=guild)
        return entries[0] if entries else None
    def format_growth_hall_line(guild, gid, label, entry):
        if not entry:
            return f"[{label}]\n└ 아직 5판 이상 티어상승 기록이 없습니다."
        name = get_hall_display_name(guild, gid, entry["uid"])
        score_text = f"{entry['start']}점 → {entry['current']}점"
        growth_text = f"+{entry['growth']}점"
        record_text = f"{entry['wins']}승 {entry['losses']}패"
        return (
            f"[{label}] {name}\n"
            f"{format_hall_detail_line(score_text, growth_text, record_text)}"
        )
    def build_hall_tier_growth_embed(guild, gid):
        lines = [
            format_growth_hall_line(guild, gid, role, get_best_role_growth_entry(gid, role, guild=guild))
            for role in ROLES
        ]
        overall = get_best_overall_growth_entry(gid, guild=guild)
        if overall:
            name = get_hall_display_name(guild, gid, overall["uid"])
            score_text = f"{overall['start']}점 → {overall['current']}점"
            growth_text = f"+{overall['growth']}점"
            record_text = f"{overall['wins']}승 {overall['losses']}패"
            role_text = f"{overall['roles']}라인"
            lines.append(
                f"[전체] {name}\n"
                f"{format_hall_detail_line(score_text, growth_text, record_text, role_text)}"
            )
        else:
            lines.append("**[전체]** 아직 5판 이상 티어상승 기록이 없습니다.")

        embed = discord.Embed(
            title="🏛️ 명예의 전당 · 티어상승",
            description="\n".join(lines),
            color=0x2ecc71
        )
        embed.set_footer(text=f"각 라인 {HALL_OF_FAME_MIN_ROLE_GAMES}판 이상 · 배치 점수 대비 현재 MMR 상승폭 기준")
        return embed
    def get_all_laner_entries(gid, guild=None):
        entries = []
        for uid, data in iter_public_user_records(guild, gid):
            user_info = ensure_user_format(data)
            if not all(int(user_info.get("plays", {}).get(role, 0) or 0) >= HALL_OF_FAME_MIN_ROLE_GAMES for role in ROLES):
                continue
            role_scores = [int(user_info.get("mmr", {}).get(role, 0) or 0) for role in ROLES]
            if any(score <= 0 for score in role_scores):
                continue
            avg_mmr = int(sum(role_scores) / len(role_scores))
            total_games = sum(int(user_info.get("plays", {}).get(role, 0) or 0) for role in ROLES)
            total_wins = 0
            total_losses = 0
            for role in ROLES:
                wins, losses = get_hall_role_record(gid, uid, user_info, role)
                total_wins += wins
                total_losses += losses
            entries.append((uid, avg_mmr, min(role_scores), max(role_scores), total_games, total_wins, total_losses))
        entries.sort(key=lambda item: (item[1], item[2], item[5]), reverse=True)
        return entries
    def build_hall_all_laner_embed(guild, gid):
        entries = get_all_laner_entries(gid, guild=guild)
        if not entries:
            description = f"아직 5개 라인을 모두 {HALL_OF_FAME_MIN_ROLE_GAMES}판 이상 플레이한 기록자가 없습니다."
        else:
            lines = []
            for rank, (uid, avg_mmr, min_mmr, max_mmr, total_games, wins, losses) in enumerate(entries[:HALL_OF_FAME_TOP_LIMIT], 1):
                name = get_hall_display_name(guild, gid, uid)
                lines.append(f"{format_hall_name_line(rank, name)}\n{format_hall_detail_line(f'5라인 평균 {avg_mmr}점', f'최저 {min_mmr}점', f'최고 {max_mmr}점', f'{total_games}판 {wins}승 {losses}패')}")
            description = "\n".join(lines)

        embed = discord.Embed(
            title="🏛️ 명예의 전당 · 올라운더",
            description=description,
            color=0x1abc9c
        )
        embed.set_footer(text=f"5개 라인 모두 {HALL_OF_FAME_MIN_ROLE_GAMES}판 이상 플레이한 유저 중 5라인 평균 MMR 상위권")
        return embed
    def get_rookie_growth_entries(gid, guild=None):
        entries = []
        for uid, data in iter_public_user_records(guild, gid):
            user_info = ensure_user_format(data)
            total_games = sum(int(user_info.get("plays", {}).get(role, 0) or 0) for role in ROLES)
            if total_games < HALL_OF_FAME_MIN_ROLE_GAMES or total_games > HALL_OF_FAME_ROOKIE_MAX_GAMES:
                continue

            role_entries = []
            for role in ROLES:
                games = int(user_info.get("plays", {}).get(role, 0) or 0)
                start = get_role_initial_mmr(user_info, role, 0)
                current = int(user_info.get("mmr", {}).get(role, 0) or 0)
                if games > 0 and start > 0 and current > 0:
                    role_entries.append((role, start, current, games))
            if not role_entries:
                continue

            start_avg = int(sum(item[1] * item[3] for item in role_entries) / sum(item[3] for item in role_entries))
            current_avg = int(sum(item[2] * item[3] for item in role_entries) / sum(item[3] for item in role_entries))
            growth = current_avg - start_avg
            if growth <= 0:
                continue
            total_wins = 0
            total_losses = 0
            for role, _start, _current, _games in role_entries:
                wins, losses = get_hall_role_record(gid, uid, user_info, role)
                total_wins += wins
                total_losses += losses
            entries.append((uid, growth, start_avg, current_avg, total_games, total_wins, total_losses))
        entries.sort(key=lambda item: (item[1], item[3], item[5]), reverse=True)
        return entries
    def build_hall_rookie_embed(guild, gid):
        entries = get_rookie_growth_entries(gid, guild=guild)
        if not entries:
            description = f"아직 신인왕 후보가 없습니다. 총 {HALL_OF_FAME_MIN_ROLE_GAMES}~{HALL_OF_FAME_ROOKIE_MAX_GAMES}판 유저 중 배치 점수 대비 MMR 상승 기록을 집계합니다."
        else:
            lines = []
            for rank, (uid, growth, start_avg, current_avg, games, wins, losses) in enumerate(entries[:HALL_OF_FAME_TOP_LIMIT], 1):
                name = get_hall_display_name(guild, gid, uid)
                lines.append(f"{format_hall_name_line(rank, name)}\n{format_hall_detail_line(f'{start_avg}점 → {current_avg}점', f'+{growth}점', f'{games}판', f'{wins}승 {losses}패')}")
            description = "\n".join(lines)

        embed = discord.Embed(
            title="🏛️ 명예의 전당 · 신인왕",
            description=description,
            color=0x2ecc71
        )
        embed.set_footer(text=f"신인왕: 총 {HALL_OF_FAME_MIN_ROLE_GAMES}~{HALL_OF_FAME_ROOKIE_MAX_GAMES}판 유저 중 배치 점수 대비 MMR 상승폭 기준")
        return embed
    def get_upset_entries(gid, guild=None):
        stats = defaultdict(lambda: {
            "games": 0,
            "wins": 0,
            "losses": 0,
            "best_gap": 0,
            "total_gap": 0,
            "roles": defaultdict(int),
        })
        for record in get_valid_match_history(gid):
            mode = record.get("mode", "classic")
            if mode not in ("classic", LOW_TIER_MODE_KEY, NOBAN_MODE_KEY):
                continue
            players = record.get("players", []) or []
            by_team_role = {}
            for player in players:
                role = player.get("role")
                team = player.get("team")
                before = player.get("before_mmr", player.get("lineup_mmr"))
                if role in ROLES and team in ("blue", "red") and isinstance(before, int):
                    by_team_role[(team, role)] = player

            for player in players:
                uid = str(player.get("user_id"))
                if not is_current_guild_member(guild, uid):
                    continue
                role = player.get("role")
                team = player.get("team")
                before = player.get("before_mmr", player.get("lineup_mmr"))
                result = player.get("result")
                if role not in ROLES or team not in ("blue", "red") or result not in ("win", "loss") or not isinstance(before, int):
                    continue
                opponent_team = "red" if team == "blue" else "blue"
                opponent = by_team_role.get((opponent_team, role))
                if not opponent:
                    continue
                opponent_mmr = opponent.get("before_mmr", opponent.get("lineup_mmr"))
                if not isinstance(opponent_mmr, int):
                    continue
                gap = opponent_mmr - before
                if gap < 200:
                    continue
                item = stats[uid]
                item["games"] += 1
                if result == "win":
                    item["wins"] += 1
                else:
                    item["losses"] += 1
                item["best_gap"] = max(item["best_gap"], gap)
                item["total_gap"] += gap
                item["roles"][role] += 1

        entries = []
        for uid, item in stats.items():
            games = int(item["games"] or 0)
            wins = int(item["wins"] or 0)
            losses = int(item["losses"] or 0)
            winrate = wins / games * 100 if games else 0.0
            avg_gap = item["total_gap"] / games if games else 0
            main_role = max(item["roles"].items(), key=lambda role_item: role_item[1])[0] if item["roles"] else "-"
            entries.append((uid, games, wins, losses, winrate, item["best_gap"], avg_gap, main_role))
        entries.sort(key=lambda item: (item[2], item[4], item[5], item[1]), reverse=True)
        return entries
    def build_hall_upset_embed(guild, gid):
        entries = get_upset_entries(gid, guild=guild)
        if not entries:
            description = "아직 업셋 매치 기록이 없습니다. 같은 라인에서 400점 이상 높은 MMR 상대를 만나 이긴 경기를 중심으로 집계합니다."
        else:
            lines = []
            for rank, (uid, games, wins, losses, winrate, best_gap, avg_gap, main_role) in enumerate(entries[:HALL_OF_FAME_TOP_LIMIT], 1):
                name = get_hall_display_name(guild, gid, uid)
                lines.append(
                    f"{format_hall_name_line(rank, name)}\n"
                    f"{format_hall_detail_line(f'업셋 성공 {wins}회', f'승률 {winrate:.1f}%', f'{games}전 {wins}승 {losses}패', f'최대 열세 {best_gap}점', f'주 라인 {main_role}')}"
                )
            description = "\n".join(lines)

        embed = discord.Embed(
            title="🏛️ 명예의 전당 · 업셋",
            description=description,
            color=0xe67e22
        )
        embed.set_footer(text="업셋: 같은 라인에서 400점 이상 높은 MMR 상대를 이긴 경기 기준 · 정렬: 성공 수 > 승률 > 최대 열세")
        return embed
    def get_winrate_reign_store(gid):
        guild_data = bot.user_data.setdefault(gid, {})
        store = guild_data.setdefault(WINRATE_REIGN_KEY, {})
        store.setdefault("daily_leaders", {})
        store.setdefault("started_at", WINRATE_REIGN_START_DATE)
        return store
    def get_current_winrate_leader(gid, guild=None):
        entries = []
        for uid, data in iter_public_user_records(guild, gid):
            user_info = ensure_user_format(data)
            wins = int(user_info.get("win", 0) or 0)
            losses = int(user_info.get("loss", 0) or 0)
            games = wins + losses
            if games < HALL_OF_FAME_WINRATE_MIN_GAMES:
                continue
            winrate = wins / games * 100
            entries.append((uid, winrate, games, wins, losses))
        if not entries:
            return None
        uid, winrate, games, wins, losses = max(entries, key=lambda item: (item[1], item[2], item[3]))
        return {
            "uid": str(uid),
            "winrate": round(winrate, 3),
            "games": int(games),
            "wins": int(wins),
            "losses": int(losses),
        }
    def record_winrate_reign_snapshot(gid, when=None, guild=None):
        leader = get_current_winrate_leader(gid, guild=guild)
        if not leader:
            return False

        current_time = when or now_kst()
        date_key = current_time.strftime("%Y-%m-%d")
        store = get_winrate_reign_store(gid)
        daily_leaders = store.setdefault("daily_leaders", {})
        previous = daily_leaders.get(date_key)
        leader["recorded_at"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
        if previous == leader:
            return False
        daily_leaders[date_key] = leader
        return True
    def get_winrate_reign_entries(gid, guild=None):
        store = bot.user_data.get(gid, {}).get(WINRATE_REIGN_KEY, {})
        daily_map = store.get("daily_leaders", {}) if isinstance(store, dict) else {}
        daily_leaders = []
        for date_text, leader in sorted(daily_map.items()):
            if not isinstance(leader, dict) or not leader.get("uid"):
                continue
            if not is_current_guild_member(guild, leader.get("uid")):
                continue
            try:
                leader_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            except ValueError:
                continue
            daily_leaders.append({
                "date": leader_date,
                "uid": str(leader.get("uid")),
                "winrate": float(leader.get("winrate", 0) or 0),
                "games": int(leader.get("games", 0) or 0),
                "wins": int(leader.get("wins", 0) or 0),
                "losses": int(leader.get("losses", 0) or 0),
            })

        periods = []
        current = None
        for leader in daily_leaders:
            if current and current["uid"] == leader["uid"]:
                current["end"] = leader["date"]
                current["days"] += 1
                current["best_wr"] = max(current["best_wr"], leader["winrate"])
                current["games"] = leader["games"]
                current["wins"] = leader["wins"]
                current["losses"] = leader["losses"]
                continue
            if current:
                periods.append(current)
            current = {
                "uid": leader["uid"],
                "start": leader["date"],
                "end": leader["date"],
                "days": 1,
                "best_wr": leader["winrate"],
                "games": leader["games"],
                "wins": leader["wins"],
                "losses": leader["losses"],
            }
        if current:
            periods.append(current)

        periods.sort(key=lambda item: (item["days"], item["best_wr"], item["games"]), reverse=True)
        return periods
    def build_hall_winrate_reign_embed(guild, gid):
        entries = get_winrate_reign_entries(gid, guild=guild)
        if not entries:
            description = f"아직 장기집권 기록이 없습니다. {WINRATE_REIGN_START_DATE}부터 승률 {HALL_OF_FAME_WINRATE_MIN_GAMES}전 이상 1위를 기록합니다."
        else:
            lines = []
            for rank, item in enumerate(entries[:WINRATE_REIGN_TOP_LIMIT], 1):
                name = get_hall_display_name(guild, gid, item["uid"])
                start_text = item["start"].strftime("%m/%d")
                end_text = item["end"].strftime("%m/%d")
                range_text = start_text if item["start"] == item["end"] else f"{start_text} ~ {end_text}"
                days_text = f"{item['days']}경기일동안 1위"
                wr_text = f"최고 {item['best_wr']:.1f}%"
                record_text = f"{item['games']}전 {item['wins']}승 {item['losses']}패"
                lines.append(
                    f"{format_hall_name_line(rank, name)}\n"
                    f"{format_hall_detail_line(days_text, f'({range_text})', wr_text, record_text)}"
                )
            description = "\n".join(lines)

        embed = discord.Embed(
            title="🏛️ 명예의 전당 · 장기집권",
            description=description,
            color=0x8e44ad
        )
        embed.set_footer(text=f"{WINRATE_REIGN_START_DATE}부터 저장된 승률 1위 유지 구간 · 최소 {HALL_OF_FAME_WINRATE_MIN_GAMES}전 · TOP {WINRATE_REIGN_TOP_LIMIT}")
        return embed
    def build_hall_overview_embed(guild, gid):
        entries = get_overall_growth_entries(gid, guild=guild)
        if not entries:
            description = "아직 전체 티어상승 기록이 없습니다."
        else:
            lines = []
            for rank, entry in enumerate(entries[:HALL_OF_FAME_TOP_LIMIT], 1):
                name = get_hall_display_name(guild, gid, entry["uid"])
                growth_text = f"+{entry['growth']}점"
                role_text = f"{entry['roles']}라인"
                game_text = f"{entry['games']}판"
                record_text = f"{entry['wins']}승 {entry['losses']}패"
                lines.append(
                    f"{format_hall_name_line(rank, name)}\n"
                    f"{format_hall_detail_line(growth_text, role_text, game_text, record_text)}"
                )
            description = "\n".join(lines)

        embed = discord.Embed(
            title="🏛️ 명예의 전당 · 전체 평균 MMR 상승",
            description=description,
            color=0x9b59b6
        )
        embed.set_footer(text=f"라인별 {HALL_OF_FAME_MIN_ROLE_GAMES}판 이상 기록의 평균 MMR 상승폭 기준")
        return embed
    def format_league_hall_team_line(guild, gid, team, fallback_label=None):
        team_no = team.get("team_no")
        team_name = str(team.get("name") or "").strip()
        label = team_name if team_name else (fallback_label or f"{team_no}팀")
        players = [
            compact_riot_name(get_member_display_name(guild, gid, uid))
            for uid in team.get("players", [])
            if is_current_guild_member(guild, uid)
        ]
        names = "\n".join(f"└ {name}" for name in players[:5]) if players else "└ 기록 없음"
        return f"**{discord.utils.escape_markdown(label)}**\n{names}"
    def build_hall_league_recent_embed(guild, gid):
        champions = list(get_league_champions(gid) or [])
        recent = [
            item
            for item in sorted(champions, key=lambda item: int(item.get("round", 0) or 0), reverse=True)
            if any(
                is_current_guild_member(guild, uid)
                for team_key in ("winner", "runner_up", "third_place")
                for uid in (item.get(team_key, {}) or {}).get("players", [])
            )
        ][:5]
        embed = discord.Embed(
            title="🏛️ 명예의 전당 · 협곡 리그전 최근 기록",
            color=0xf1c40f
        )
        if not recent:
            embed.description = "아직 기록된 협곡 리그전 우승팀이 없습니다."
            return embed

        for record in recent:
            round_no = int(record.get("round", 0) or 0)
            winner = record.get("winner", {}) or {}
            runner_up = record.get("runner_up", {}) or {}
            third_place = record.get("third_place", {}) or {}
            value = (
                f"🥇 우승\n{format_league_hall_team_line(guild, gid, winner, f'{round_no}회차 우승팀')}\n\n"
                f"🥈 준우승\n{format_league_hall_team_line(guild, gid, runner_up, f'{round_no}회차 준우승팀')}"
            )
            if third_place:
                value += (
                    f"\n\n🥉 3등\n{format_league_hall_team_line(guild, gid, third_place, f'{round_no}회차 3등')}"
                )
            embed.add_field(
                name=f"🏆 협곡 리그전 {round_no}회차",
                value=value,
                inline=False
            )
        embed.set_footer(text="최근 5회차 기준 · 결승 결과와 우승팀 이름 입력이 완료된 기록만 표시됩니다.")
        return embed
    def get_league_detail_rank_stats(gid, guild=None):
        guild_data = bot.user_data.setdefault(gid, {})
        league_match_ids = {
            str(record.get("id"))
            for record in get_valid_match_history(gid)
            if record.get("mode") == LEAGUE_MODE_KEY and record.get("id")
        }
        store = match_stats.get_store(guild_data)
        stats = defaultdict(lambda: {
            "mvp": 0,
            "ace": 0,
            "games": 0,
            "kills": 0,
            "deaths": 0,
            "assists": 0,
        })
        skipped = 0
        for match_id in league_match_ids:
            match_entries = store.get(match_id, {}) or {}
            if not match_entries:
                continue
            try:
                awards = match_stats.score_match_awards(guild_data, match_id)
            except Exception:
                skipped += 1
                logger.exception("토너먼트 명예의전당 상세스탯 수상 계산 실패: %s", match_id)
                awards = {}
            for award_key in ("mvp", "ace"):
                award = awards.get(award_key)
                if not award:
                    continue
                uid = str(award.get("user_id"))
                if uid and uid != "None" and is_current_guild_member(guild, uid):
                    stats[uid][award_key] += 1
            for entry in match_entries.values():
                uid = str(entry.get("user_id"))
                if not uid or uid == "None" or not is_current_guild_member(guild, uid):
                    continue
                bucket = stats[uid]
                bucket["games"] += 1
                bucket["kills"] += safe_detail_int(entry.get("kills"))
                bucket["deaths"] += safe_detail_int(entry.get("deaths"))
                bucket["assists"] += safe_detail_int(entry.get("assists"))
        return stats, skipped
    def format_hall_joint_people(guild, gid, rows, value_text):
        if not rows:
            return "기록 없음"
        joint_text = " (공동)" if len(rows) > 1 else ""
        names = ", ".join(f"**{get_hall_display_name(guild, gid, uid)}**" for uid in rows)
        return f"{names}{joint_text}\n└ {value_text}"
    def get_max_league_stat_rows(gid, stat_key, guild=None):
        rows = []
        for uid, data in iter_public_user_records(guild, gid):
            league = ensure_user_format(data).get("league_stats", {})
            value = int(league.get(stat_key, 0) or 0)
            if value > 0:
                rows.append((str(uid), value))
        if not rows:
            return [], 0
        max_value = max(value for _, value in rows)
        return [uid for uid, value in rows if value == max_value], max_value
    def build_hall_league_ranking_embed(guild, gid):
        win_uids, win_count = get_max_league_stat_rows(gid, "wins", guild=guild)
        runner_uids, runner_count = get_max_league_stat_rows(gid, "runner_ups", guild=guild)

        winrate_rows = []
        for uid, data in iter_public_user_records(guild, gid):
            league = ensure_user_format(data).get("league_stats", {})
            wins = int(league.get("match_win", 0) or 0)
            losses = int(league.get("match_loss", 0) or 0)
            games = wins + losses
            if games <= 0:
                continue
            winrate_rows.append((str(uid), wins / games * 100, games, wins, losses))
        best_wr = max(winrate_rows, key=lambda item: (item[1], item[2], item[3]), default=None)

        detail_stats, skipped = get_league_detail_rank_stats(gid, guild=guild)
        max_mvp = max((item["mvp"] for item in detail_stats.values()), default=0)
        mvp_uids = [uid for uid, item in detail_stats.items() if max_mvp > 0 and item["mvp"] == max_mvp]
        max_ace = max((item["ace"] for item in detail_stats.values()), default=0)
        ace_uids = [uid for uid, item in detail_stats.items() if max_ace > 0 and item["ace"] == max_ace]

        kda_rows = []
        for uid, item in detail_stats.items():
            games = int(item["games"] or 0)
            if games <= 0:
                continue
            kda = (int(item["kills"]) + int(item["assists"])) / max(1, int(item["deaths"]))
            kda_rows.append((uid, kda, games, int(item["kills"]), int(item["deaths"]), int(item["assists"])))
        best_kda = max(kda_rows, key=lambda item: (item[1], item[2], item[3] + item[5]), default=None)

        embed = discord.Embed(
            title="🏛️ 명예의 전당 · 협곡 리그전 랭킹",
            color=0x9b59b6
        )
        embed.add_field(
            name="🏆 최다 우승자",
            value=format_hall_joint_people(guild, gid, win_uids, f"우승 **{win_count}회**") if win_uids else "기록 없음",
            inline=False
        )
        embed.add_field(
            name="🥈 최다 준우승자",
            value=format_hall_joint_people(guild, gid, runner_uids, f"준우승 **{runner_count}회**") if runner_uids else "기록 없음",
            inline=False
        )
        if best_wr:
            uid, winrate, games, wins, losses = best_wr
            wr_value = f"**{get_hall_display_name(guild, gid, uid)}**\n└ 매치 승률 **{winrate:.1f}%** · {games}전 {wins}승 {losses}패"
        else:
            wr_value = "기록 없음"
        embed.add_field(name="⚔️ 최고 매치 승률", value=wr_value, inline=False)
        embed.add_field(
            name="🌟 최다 MVP",
            value=format_hall_joint_people(guild, gid, mvp_uids, f"MVP **{max_mvp}회**") if mvp_uids else "ROFL 상세스탯 기록 없음",
            inline=False
        )
        embed.add_field(
            name="🛡️ 최다 ACE",
            value=format_hall_joint_people(guild, gid, ace_uids, f"ACE **{max_ace}회**") if ace_uids else "ROFL 상세스탯 기록 없음",
            inline=False
        )
        if best_kda:
            uid, kda, games, kills, deaths, assists = best_kda
            kda_value = f"**{get_hall_display_name(guild, gid, uid)}**\n└ KDA **{kda:.2f}** · {games}전 · {kills}/{deaths}/{assists}"
        else:
            kda_value = "ROFL 상세스탯 기록 없음"
        embed.add_field(name="📈 최고 KDA", value=kda_value, inline=False)
        footer = "협곡 리그전 기록 기준 · MVP/ACE/KDA는 ROFL 상세스탯이 저장된 리그전 경기만 집계합니다."
        if skipped:
            footer += f" · 수상 계산 제외 {skipped}경기"
        embed.set_footer(text=footer)
        return embed
    @bot.tree.command(name="명예의전당", description="서버의 주요 개인/라인/장기/리그전 기록을 확인합니다.")
    @app_commands.describe(선택="확인할 명예의 전당 카테고리입니다.")
    @app_commands.choices(선택=[
        app_commands.Choice(name="전체", value="전체"),
        app_commands.Choice(name="개인기록", value="개인기록"),
        app_commands.Choice(name="라인기록", value="라인기록"),
        app_commands.Choice(name="장기기록", value="장기기록"),
        app_commands.Choice(name="협곡 리그전", value="토너먼트"),
    ])
    async def hall_of_fame(interaction: discord.Interaction, 선택: str = "전체"):
        gid = str(interaction.guild_id)
        if gid not in bot.user_data or not bot.user_data[gid]:
            return await interaction.response.send_message("🏛️ 아직 명예의 전당에 표시할 데이터가 없습니다.", ephemeral=True)

        await interaction.response.defer()
        selected = 선택 or "전체"
        if selected == "개인기록":
            embeds = [
                build_hall_streak_embed(interaction.guild, gid),
                build_hall_tier_growth_embed(interaction.guild, gid),
                build_hall_all_laner_embed(interaction.guild, gid),
                build_hall_rookie_embed(interaction.guild, gid),
                build_hall_upset_embed(interaction.guild, gid),
            ]
        elif selected == "라인기록":
            embeds = [build_hall_role_mmr_embed(interaction.guild, gid, role) for role in ROLES]
        elif selected == "장기기록":
            if record_winrate_reign_snapshot(gid, guild=interaction.guild):
                bot.save_lucid_data(gid)
            embeds = [build_hall_winrate_reign_embed(interaction.guild, gid)]
        elif selected == "토너먼트":
            embeds = [
                build_hall_league_recent_embed(interaction.guild, gid),
                build_hall_league_ranking_embed(interaction.guild, gid),
            ]
        else:
            embeds = [build_hall_overview_embed(interaction.guild, gid)]
        await interaction.followup.send(embeds=embeds[:10])
    def get_overall_record_stats(user_info):
        user_info = ensure_user_format(user_info)
        wins = user_info.get('win', 0)
        losses = user_info.get('loss', 0)
        games = wins + losses
        winrate = (wins / games * 100) if games else 0.0
        return games, wins, losses, winrate
    def format_record_ranking_line(rank, guild, gid, uid, games, wins, losses, winrate, primary="games"):
        name = get_member_display_name(guild, gid, uid)
        if primary == "winrate":
            summary = f"승률 **{winrate:.1f}%** · {games}전 {wins}승 {losses}패"
        else:
            summary = f"**{games}전** {wins}승 {losses}패 · 승률 {winrate:.1f}%"
        return f"**{rank}위** | `{name}` · {summary}"
    async def games_ranking(interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        if gid not in bot.user_data or not bot.user_data[gid]:
            return await interaction.response.send_message(
                "📊 서버 내에 축적된 소환사 데이터베이스가 존재하지 않습니다.",
                ephemeral=True
            )

        entries = []
        for uid, data in iter_public_user_records(interaction.guild, gid):
            games, wins, losses, winrate = get_overall_record_stats(data)
            if games > 0:
                entries.append((uid, games, wins, losses, winrate))

        if not entries:
            return await interaction.response.send_message("📊 아직 판수랭킹에 표시할 일반 내전 기록이 없습니다.", ephemeral=True)

        entries.sort(key=lambda item: (item[1], item[2], item[4]), reverse=True)
        lines = [
            format_record_ranking_line(rank, interaction.guild, gid, uid, games, wins, losses, winrate)
            for rank, (uid, games, wins, losses, winrate) in enumerate(entries[:10], 1)
        ]
        embed = discord.Embed(
            title="🎮 일반 내전 판수랭킹 TOP 10",
            description="\n".join(lines),
            color=0x3498db
        )
        embed.add_field(
            name="집계 기준",
            value="일반 내전 전체 전적 기준",
            inline=False
        )
        embed.set_footer(text=PROMO_FOOTER)
        await interaction.response.send_message(embed=embed)
    async def winrate_ranking(interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        if gid not in bot.user_data or not bot.user_data[gid]:
            return await interaction.response.send_message(
                "📊 서버 내에 축적된 소환사 데이터베이스가 존재하지 않습니다.",
                ephemeral=True
            )

        entries = []
        all_records = {}
        for uid, data in iter_public_user_records(interaction.guild, gid):
            games, wins, losses, winrate = get_overall_record_stats(data)
            all_records[str(uid)] = (games, wins, losses, winrate)
            if games >= 10:
                entries.append((uid, games, wins, losses, winrate))

        if not entries:
            return await interaction.response.send_message("📊 아직 승률랭킹에 표시할 10전 이상 소환사가 없습니다.", ephemeral=True)

        entries.sort(key=lambda item: (item[4], item[1], item[2]), reverse=True)
        lines = [
            format_record_ranking_line(rank, interaction.guild, gid, uid, games, wins, losses, winrate, primary="winrate")
            for rank, (uid, games, wins, losses, winrate) in enumerate(entries[:10], 1)
        ]
        embed = discord.Embed(
            title="📈 일반 내전 승률랭킹 TOP 10",
            description="\n".join(lines),
            color=0x2ecc71
        )

        requester_uid = str(interaction.user.id)
        requester_record = all_records.get(requester_uid)
        if requester_record:
            games, wins, losses, winrate = requester_record
            if games >= 10:
                requester_rank = next(
                    (rank for rank, (uid, *_rest) in enumerate(entries, 1) if str(uid) == requester_uid),
                    None
                )
                if requester_rank:
                    embed.add_field(
                        name="내 순위",
                        value=f"**{requester_rank}위** · 승률 **{winrate:.1f}%** · {games}전 {wins}승 {losses}패",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="내 기록",
                    value=f"승률 **{winrate:.1f}%** · {games}전 {wins}승 {losses}패\n랭킹 집계 기준: 최소 10전 이상",
                    inline=False
                )

        embed.add_field(
            name="집계 기준",
            value="최소 10전 이상 일반 내전 기록\n동률: 승률 > 판수 > 승수",
            inline=False
        )
        embed.set_footer(text=PROMO_FOOTER)
        await interaction.response.send_message(embed=embed)
    @bot.tree.command(name="티어기준", description="내전 시스템에 따른 랭크 티어 배정 기준표를 확인합니다.")
    async def tier_info(interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        frequency_config = get_match_frequency_config(gid)
        provisional_config = get_provisional_mmr_config(gid)
        embed = discord.Embed(
            title="🏆 Dream To Play 내전 레이팅 기준표", 
            description="전적과 동일한 사용자 표시 기준입니다.",
            color=0x3498db
        )
        embed.add_field(
            name="👑 마스터 이상",
            value=(
                f"{get_tier_emoji('챌린저 (LoL)', interaction.guild, gid)} **챌린저** `800점 이상`\n"
                f"{get_tier_emoji('그랜드마스터 (LoL)', interaction.guild, gid)} **그랜드마스터** `400~799점`\n"
                f"{get_tier_emoji('마스터 (LoL)', interaction.guild, gid)} **마스터** `0~399점`"
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 다이아 이하",
            value=(
                "아이언 → 브론즈 → 실버 → 골드 → 플래티넘 → 에메랄드 → 다이아\n"
                "각 티어 `IV → III → II → I` · 단계별 `0~99점`\n"
                "`100점` 도달 시 다음 단계로 즉시 승급"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎯 점수 분배 기준",
            value=(
                f"🐣 **배치** · 라인별 {frequency_config['placement_games']}판 미만 `기본 ±{frequency_config['placement_delta']}점`\n"
                f"⚔️ **정규** · 라인별 {frequency_config['placement_games']}판 이상 `기본 ±{frequency_config['regular_delta']}점`\n"
                f"🟡 **임시 배치** · 관리자 지정 {provisional_config['games']}판 `기본 ±{provisional_config['delta']}점` · 경기력과 상대에 따라 조정\n"
                "🔥 **연승·연패** · 같은 라인에서 결과가 이어지면 추가 보정"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)
    def build_my_info_embed(guild, gid, uid_str, user_data, member=None):
        # 명령에서 전달한 discord.Member를 우선 사용합니다.
        # Member가 없을 때만 guild 캐시에서 다시 찾습니다.
        if member is None and guild is not None:
            try:
                member = guild.get_member(int(uid_str))
            except (TypeError, ValueError):
                member = None

        user_data = ensure_user_format(user_data)
        avg_mmr = get_avg_mmr(user_data['mmr'])
        wins = user_data['win']
        losses = user_data['loss']
        total_games = wins + losses

        peak_role, peak_mmr = get_peak_role_mmr(user_data['mmr'])
        embed_tier = get_tier_name(peak_mmr) if peak_role else get_tier_name(avg_mmr)
        
        win_rate = (wins / total_games * 100) if total_games > 0 else 0.0
        most_role, most_ratio = get_most_played_role(user_data['plays'])
        streak_status = format_streak_display(user_data.get('streak', 0))

        fallback_name = getattr(member, "display_name", f"UID {uid_str}")
        lol_name = user_data.get('lol_name', fallback_name)
        equipped_title = get_equipped_title(user_data)
        embed = discord.Embed(
            title=f"📝 {lol_name}님의 정보",
            color=TIER_DATA[embed_tier]['color']
        )
        
        # 서버별 프로필 사진 → 일반 프로필 → Discord 기본 아바타 순서.
        # display_avatar는 보통 폴백을 포함하지만 default_avatar까지 명시해
        # 썸네일이 비어 버리는 경우를 방지합니다.
        avatar = (
            getattr(member, "guild_avatar", None)
            or getattr(member, "display_avatar", None)
            or getattr(member, "avatar", None)
            or getattr(member, "default_avatar", None)
        )
        # Discord의 움직이는 GIF 아바타는 일부 임베드 환경에서 썸네일이
        # 비어 보일 수 있으므로, 프로필 임베드에서는 정적인 PNG 프레임으로
        # 변환해 표시합니다. 일반 정적 아바타는 그대로 사용합니다.
        thumbnail_avatar = avatar
        if avatar is not None:
            try:
                if callable(getattr(avatar, "is_animated", None)) and avatar.is_animated():
                    thumbnail_avatar = avatar.with_static_format("png")
            except (AttributeError, TypeError, ValueError):
                thumbnail_avatar = avatar

        avatar_url = getattr(thumbnail_avatar, "url", None)
        if avatar_url:
            embed.set_thumbnail(url=str(avatar_url))

        peak_value = format_profile_role_score(peak_role, peak_mmr, guild, gid) if peak_role else "기록 없음"
        most_value = f"{get_role_display_marker(most_role, guild)} {most_role} ({most_ratio:.1f}%)" if most_role else "없음"
        peak_records = update_peak_records(user_data)
        bot.save_lucid_data(gid)
        best_streak = int(peak_records.get('best_streak', 0) or 0)
        best_mmr = int(peak_records.get('best_mmr', 0) or 0)
        best_mmr_role = peak_records.get('best_mmr_role')
        best_mmr_value = (
            format_profile_role_score(best_mmr_role, best_mmr, guild, gid)
            if best_mmr_role and best_mmr > 0 else "기록 없음"
        )
        event_stats = user_data.get('event_stats', {}).get(EVENT_MODE_KEY, {'win': 0, 'loss': 0})
        event_wins = safe_detail_int(event_stats.get('win', 0))
        event_losses = safe_detail_int(event_stats.get('loss', 0))
        event_total = event_wins + event_losses
        aram_stats = user_data.get('event_stats', {}).get(ARAM_MODE_KEY, {'win': 0, 'loss': 0})
        aram_wins = safe_detail_int(aram_stats.get('win', 0))
        aram_losses = safe_detail_int(aram_stats.get('loss', 0))
        aram_total = aram_wins + aram_losses
        event_lines = []
        if event_total > 0:
            event_lines.append(f"{EVENT_MODE_NAME} **{event_total}전 {event_wins}승 {event_losses}패**")
        if aram_total > 0:
            event_lines.append(f"{ARAM_MODE_NAME} **{aram_total}전 {aram_wins}승 {aram_losses}패**")
        aram_league_stats = user_data.get('aram_league_stats', {})
        aram_league_match_win = safe_detail_int(aram_league_stats.get('match_win', 0))
        aram_league_match_loss = safe_detail_int(aram_league_stats.get('match_loss', 0))
        aram_league_participations = safe_detail_int(aram_league_stats.get('participations', 0))
        aram_league_wins = safe_detail_int(aram_league_stats.get('wins', 0))
        if aram_league_match_win + aram_league_match_loss + aram_league_participations > 0:
            event_lines.append(
                f"{ARAM_LEAGUE_MODE_NAME} **매치 {aram_league_match_win}승 {aram_league_match_loss}패 · 참가 {aram_league_participations}회 · 우승 {aram_league_wins}회**"
            )

        league_stats = user_data.get('league_stats', {})
        league_match_wins = league_stats.get('match_win', 0)
        league_match_losses = league_stats.get('match_loss', 0)
        league_match_total = league_match_wins + league_match_losses
        league_participations = league_stats.get('participations', 0)
        league_wins = league_stats.get('wins', 0)
        league_runner_ups = league_stats.get('runner_ups', 0)
        league_third_places = league_stats.get('third_places', 0)
        league_lines = []
        if league_match_total > 0 or league_participations or league_wins or league_runner_ups or league_third_places:
            league_lines.append(format_league_match_summary(league_stats))
            medal_line = format_league_medal_line(league_wins, league_runner_ups, league_third_places)
            if medal_line:
                league_lines.append(medal_line)

        description_lines = []
        if equipped_title:
            description_lines.extend([
                f"칭호: {format_user_equipped_title(guild, gid, user_data, equipped_title)}",
                "",
            ])
        description_lines.extend([
            f"**최고 라인** {peak_value}",
            f"**평균 티어** {format_profile_mmr_points(avg_mmr, guild, gid)}",
            f"**최근 흐름** {streak_status}",
            f"**주 포지션** {most_value}",
        ])
        description_lines.extend([
            "",
            "⚔️ **내전**",
        ])
        if total_games > 0:
            description_lines.extend([
                f"**{total_games}전 {wins}승 {losses}패**",
                f"승률 **{win_rate:.1f}%**",
            ])
        else:
            description_lines.append("아직 내전 기록이 없어요")
        if event_lines:
            description_lines.extend([
                "",
                f"🏟️ **이벤트**",
                *event_lines,
            ])
        if league_lines:
            description_lines.extend([
                f"🏆 **{LEAGUE_TITLE_NAME}**",
                *league_lines,
            ])
        description_lines.extend(["", ""])
        embed.description = "\n".join(description_lines)

        def format_role_mmr(role):
            score = user_data['mmr'][role]
            return format_profile_role_score(role, score, guild, gid)

        role_mmr_lines = [format_role_mmr(r) for r in ROLES if user_data['mmr'].get(r, 0) > 0]
        if role_mmr_lines:
            embed.add_field(name="📊 라인 MMR", value="\n".join(role_mmr_lines), inline=False)

        embed.add_field(
            name="📈 최고 기록",
            value=f"최고 레이팅 **{best_mmr_value}**\n최고 연승 **{best_streak}연승**",
            inline=False
        )
        noban_mmr = get_noban_mmr(user_data)
        if noban_mmr > 0:
            noban_tier = get_tier_name(noban_mmr)
            embed.add_field(
                name="🚫 노밴 MMR",
                value=f"**{format_profile_mmr_points(noban_mmr, guild, gid)}**",
                inline=True
            )
        return embed
    @bot.tree.command(name="내정보", description="자신의 상세 레이팅과 승률 지표 및 주포지션을 체크합니다.")
    async def my_info(interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        uid_str = str(interaction.user.id)

        if gid not in bot.user_data or uid_str not in bot.user_data[gid]:
            return await interaction.response.send_message(
                "⚠️ 소환사 정보가 등록되어 있지 않습니다. `/소환사등록` 명령어로 먼저 생성해주세요.", 
                ephemeral=True
            )

        await interaction.response.defer()
        user_data = bot.user_data[gid][uid_str]

        # /소환사관리 정보와 같은 Member 경로를 사용합니다.
        # 해당 명령에서 서버 프로필이 정상 표시되므로 별도 REST fetch나
        # 두 번째 set_thumbnail 없이 동일한 build 함수에 Member를 전달합니다.
        member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        member = member or interaction.user

        embed = build_my_info_embed(interaction.guild, gid, uid_str, user_data, member)
        bot.save_lucid_data(gid)
        await interaction.followup.send(embed=embed)
    def sync_permission_titles_for_member(guild, gid, member):
        if not member or str(member.id) not in bot.user_data.get(gid, {}):
            return False
        changed = False
        permissions = getattr(member, "guild_permissions", None)
        if bool(getattr(permissions, "administrator", False)):
            changed = add_title_to_user(gid, str(member.id), GENERAL_TITLE_DEFS["server_admin"]) or changed
        configured_role_id = str(bot.user_data.get(gid, {}).get(MATCH_ADMIN_ROLE_KEY) or "")
        roles = getattr(member, "roles", []) or []
        is_configured_admin = bool(configured_role_id and any(str(getattr(role, "id", "")) == configured_role_id for role in roles))
        if bool(getattr(permissions, "administrator", False)) or is_configured_admin or any(getattr(role, "name", "") == "내전 관리자" for role in roles):
            changed = add_title_to_user(gid, str(member.id), GENERAL_TITLE_DEFS["match_admin"]) or changed
        return changed
    async def title_list(interaction: discord.Interaction, season: str = "all"):
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "titles"):
            return await interaction.response.send_message(get_disabled_feature_message("titles"), ephemeral=True)
        uid = str(interaction.user.id)
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 소환사 정보가 등록되어 있지 않습니다.", ephemeral=True)

        if sync_permission_titles_for_member(interaction.guild, gid, interaction.user):
            bot.save_lucid_data(gid)
        user_info = ensure_user_format(bot.user_data[gid][uid])
        finalize_legacy_pending_custom_titles(interaction.guild, gid, uid)
        user_info = ensure_user_format(bot.user_data[gid][uid])
        titles = user_info["titles"]
        if season == TITLE_LEGACY_SEASON:
            owned = get_title_season_owned(user_info, TITLE_LEGACY_SEASON)
        elif season == TITLE_CURRENT_SEASON:
            owned = get_title_season_owned(user_info, TITLE_CURRENT_SEASON)
        else:
            owned = titles.get("owned", [])
        equipped = titles.get("equipped") or "없음"

        season_label = "전체 시즌" if season == "all" else TITLE_SEASON_LABELS.get(season, season)
        embed = discord.Embed(
            title=f"🏷️ {interaction.user.display_name} 님의 칭호 목록 · {season_label}",
            color=0x9b59b6
        )
        embed.add_field(name="장착 중", value=f"**[{format_title_display(interaction.guild, gid, equipped)}]**" if equipped != "없음" else "없음", inline=False)
        if owned:
            owned_lines = []
            s1_owned_set = set(get_title_season_owned(user_info, TITLE_LEGACY_SEASON))
            s2_owned_set = set(get_title_season_owned(user_info, TITLE_CURRENT_SEASON))
            for title in owned:
                source_text = format_title_source_note_line(title)
                summary = format_title_condition_summary(gid, title)
                season_text = ""
                if season == "all":
                    tags = []
                    if title in s1_owned_set:
                        tags.append("S1")
                    if title in s2_owned_set:
                        tags.append("S2")
                    if tags:
                        season_text = f" `{'·'.join(tags)}`"
                owned_lines.append(f"• **{format_title_display(interaction.guild, gid, title)}**{season_text}{source_text}" + (f"\n{summary}" if summary else ""))

            chunk = []
            chunk_len = 0
            field_index = 1
            for line in owned_lines:
                next_len = len(line) + 2
                if chunk and chunk_len + next_len > 950:
                    suffix = "" if field_index == 1 else f" {field_index}"
                    embed.add_field(name=f"보유 칭호{suffix}", value="\n".join(chunk), inline=False)
                    field_index += 1
                    chunk = []
                    chunk_len = 0
                chunk.append(line)
                chunk_len += next_len
            if chunk:
                suffix = "" if field_index == 1 else f" {field_index}"
                embed.add_field(name=f"보유 칭호{suffix}", value="\n".join(chunk), inline=False)
        else:
            embed.add_field(name="보유 칭호", value="아직 보유한 칭호가 없습니다.", inline=False)
        if season == "all":
            s1_count = len(get_title_season_owned(user_info, TITLE_LEGACY_SEASON))
            s2_count = len(get_title_season_owned(user_info, TITLE_CURRENT_SEASON))
            embed.set_footer(text=f"시즌 1 {s1_count}개 · 시즌 2 {s2_count}개 · 기존 칭호도 계속 장착할 수 있습니다.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    async def admin_title_list(interaction: discord.Interaction, 유저: discord.Member):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("⚠️ 내전 관리자만 다른 유저의 칭호를 확인할 수 있습니다.", ephemeral=True)

        gid = str(interaction.guild_id)
        uid = str(유저.id)
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 해당 유저의 소환사 정보가 등록되어 있지 않습니다.", ephemeral=True)

        user_info = ensure_user_format(bot.user_data[gid][uid])
        finalize_legacy_pending_custom_titles(interaction.guild, gid, uid)
        user_info = ensure_user_format(bot.user_data[gid][uid])
        titles = user_info["titles"]
        owned = titles.get("owned", [])
        equipped = titles.get("equipped") or "없음"
        embed = discord.Embed(
            title=f"🏷️ {유저.display_name} 님의 칭호 보유 현황",
            color=0x9b59b6
        )
        embed.add_field(name="장착 중", value=f"**[{format_title_display(interaction.guild, gid, equipped)}]**" if equipped != "없음" else "없음", inline=False)
        if owned:
            owned_lines = []
            for title in owned:
                source_text = format_title_source_note_line(title)
                summary = format_title_condition_summary(gid, title)
                owned_lines.append(f"• **{format_title_display(interaction.guild, gid, title)}**{source_text}" + (f"\n{summary}" if summary else ""))

            chunk = []
            chunk_len = 0
            field_index = 1
            for line in owned_lines:
                next_len = len(line) + 2
                if chunk and chunk_len + next_len > 950:
                    suffix = "" if field_index == 1 else f" {field_index}"
                    embed.add_field(name=f"보유 칭호{suffix}", value="\n".join(chunk), inline=False)
                    field_index += 1
                    chunk = []
                    chunk_len = 0
                chunk.append(line)
                chunk_len += next_len
            if chunk:
                suffix = "" if field_index == 1 else f" {field_index}"
                embed.add_field(name=f"보유 칭호{suffix}", value="\n".join(chunk), inline=False)
        else:
            embed.add_field(name="보유 칭호", value="아직 보유한 칭호가 없습니다.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    async def owned_title_autocomplete(interaction: discord.Interaction, current: str):
        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_info = ensure_user_format(bot.user_data.setdefault(gid, {}).setdefault(uid, make_default_user(interaction.user.display_name)))
        owned = [str(title) for title in user_info.get("titles", {}).get("owned", []) if str(title).strip()]
        current_text = (current or "").strip().lower()
        if current_text:
            owned = [title for title in owned if current_text in title.lower()]
        owned = owned[:25]
        return [
            app_commands.Choice(name=title[:100], value=title[:100])
            for title in owned
        ]
    async def target_owned_title_autocomplete(interaction: discord.Interaction, current: str):
        gid = str(interaction.guild.id)
        target = interaction.namespace.유저
        if not target:
            return []
        uid = str(target.id) if hasattr(target, "id") else str(target)
        user_info = ensure_user_format(bot.user_data.setdefault(gid, {}).get(uid, make_default_user(getattr(target, "display_name", uid))))
        owned = [str(title) for title in user_info.get("titles", {}).get("owned", []) if str(title).strip()]
        current_text = (current or "").strip().lower()
        if current_text:
            owned = [title for title in owned if current_text in title.lower()]
        owned = owned[:25]
        return [
            app_commands.Choice(name=title[:100], value=title[:100])
            for title in owned
        ]
    def get_defined_title_options():
        titles = []
        titles.extend(info.get("title") for info in FIRST_TITLE_DEFS.values())
        titles.extend(GENERAL_TITLE_DEFS.values())
        titles.extend(MANUAL_TITLE_DEFS.keys())
        titles.extend(ROLE_MASTER_TITLES.values())
        titles.extend(CHAMPION_MASTERY_TITLE_OVERRIDES.values())
        seen = set()
        result = []
        for title in titles:
            title = str(title or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            result.append(title)
        return result
    def resolve_defined_title(title):
        text = str(title or "").strip()
        if not text:
            return ""
        options = get_defined_title_options()
        if text in options:
            return text
        truncated_matches = [option for option in options if option[:100] == text]
        return truncated_matches[0] if len(truncated_matches) == 1 else text
    async def defined_title_autocomplete(interaction: discord.Interaction, current: str):
        titles = get_defined_title_options()
        current_text = (current or "").strip().lower()
        if current_text:
            titles = [title for title in titles if current_text in title.lower()]
        titles = titles[:25]
        return [
            app_commands.Choice(name=title[:100], value=title[:100])
            for title in titles
        ]
    def is_first_limited_title(title):
        return any(info.get("title") == title for info in FIRST_TITLE_DEFS.values())
    USER_SEARCH_MIN_GAMES = 5
    USER_SEARCH_RECENT_GAMES = 20
    USER_SEARCH_MIN_ROLE_GAMES = 3
    USER_SEARCH_PAGE_SIZE = 1
    USER_SEARCH_HIGH_CONFIDENCE_PEERS = 10
    user_search_action_choices = [
        app_commands.Choice(name="특이점", value="특이점"),
        app_commands.Choice(name="저평가", value="저평가"),
    ]
    def _safe_mean(values, default=0.0):
        values = [float(v) for v in values if v is not None]
        return (sum(values) / len(values)) if values else float(default)
    def _bounded_ratio_delta(value, baseline, scale=1.0, limit=20.0):
        baseline = float(baseline or 0)
        if baseline <= 0:
            return 0.0
        delta = ((float(value or 0) / baseline) - 1.0) * float(scale)
        return max(-limit, min(limit, delta))
    def _user_search_role_mmr(user_info, role, samples):
        current = int(user_info.get("mmr", {}).get(role, 0) or 0)
        if current > 0:
            return current
        historical = [x["before_mmr"] for x in samples if int(x.get("before_mmr", 0) or 0) > 0]
        if historical:
            return int(round(_safe_mean(historical)))
        return int(get_avg_mmr(user_info.get("mmr", {})) or 0)
    def _build_role_metric(user_info, role, samples):
        role_samples = [x for x in samples if x["role"] == role]
        if len(role_samples) < USER_SEARCH_MIN_ROLE_GAMES:
            return None
        return {
            "role": role,
            "games": len(role_samples),
            "mmr": _user_search_role_mmr(user_info, role, role_samples),
            "score": _safe_mean([x["score"] for x in role_samples]),
            "dpm": _safe_mean([x["dpm"] for x in role_samples]),
            "kda": _safe_mean([x["kda"] for x in role_samples]),
            "kp": _safe_mean([x["kp"] for x in role_samples]),
            "winrate": _safe_mean([x["win"] for x in role_samples]) * 100,
            "award_rate": _safe_mean([x["award"] for x in role_samples]) * 100,
            "lane_gap": _safe_mean([
                x["opponent_mmr"] - x["before_mmr"]
                for x in role_samples
                if x["before_mmr"] > 0 and x["opponent_mmr"] > 0
            ]),
        }
    def _score_role_vs_peers(metric, peers):
        if not peers:
            return {
                **metric,
                "anomaly": 0.0,
                "raw_gap": 0,
                "gap": 0,
                "expected_mmr": metric["mmr"],
                "peer_count": 0,
                "peer": {},
            }

        base = {
            key: _safe_mean([p[key] for p in peers])
            for key in ("score", "dpm", "kda", "kp", "winrate", "award_rate")
        }
        anomaly = 50.0
        anomaly += _bounded_ratio_delta(metric["score"], base["score"], 35, 18)
        anomaly += _bounded_ratio_delta(metric["dpm"], base["dpm"], 18, 10)
        anomaly += _bounded_ratio_delta(metric["kda"], base["kda"], 15, 9)
        anomaly += max(-6, min(6, (metric["kp"] - base["kp"]) * 0.22))
        anomaly += max(-7, min(7, (metric["winrate"] - base["winrate"]) * 0.18))
        anomaly += max(-8, min(8, (metric["award_rate"] - base["award_rate"]) * 0.20))
        anomaly += max(-4, min(7, metric["lane_gap"] / 80.0))
        anomaly = max(0.0, min(100.0, anomaly))

        raw_gap = int(max(0, min(1200, round((anomaly - 50.0) * 18))))
        # Small peer groups are useful as a clue, but must not catapult sparse
        # Master+ populations straight to Challenger. Only 10+ peers get full weight.
        peer_factor = min(1.0, len(peers) / USER_SEARCH_HIGH_CONFIDENCE_PEERS)
        gap = int(round(raw_gap * peer_factor))

        return {
            **metric,
            "anomaly": anomaly,
            "raw_gap": raw_gap,
            "gap": gap,
            "expected_mmr": metric["mmr"] + gap,
            "peer_count": len(peers),
            "peer": base,
        }
    def build_user_search_rows(guild, gid):
        """Build one deep-dive row per user using same-role, same-MMR server peers."""
        guild_data = bot.user_data.get(gid, {})
        per_user = {}

        for match_id, match_entries in match_stats.get_store(guild_data).items():
            entries = list((match_entries or {}).values())
            if not entries:
                continue
            try:
                scored_rows = {str(row.get("user_id")): row for row in match_stats.score_entries(entries)}
                awards = match_stats.score_match_awards(guild_data, match_id)
            except Exception:
                logger.exception("유저탐색 점수 계산 제외 경기: %s", match_id)
                continue

            mvp_uid = str((awards.get("mvp") or {}).get("user_id") or "")
            ace_uid = str((awards.get("ace") or {}).get("user_id") or "")
            for entry in entries:
                uid = str(entry.get("user_id") or "")
                if not uid or uid not in guild_data:
                    continue
                role = str(entry.get("role") or "")
                if role not in ROLES:
                    continue
                scored = scored_rows.get(uid, {})
                per_user.setdefault(uid, []).append({
                    "role": role,
                    "score": float(scored.get("score", 0) or 0),
                    "dpm": float(entry.get("dpm", 0) or 0),
                    "kda": float(entry.get("kda", 0) or 0),
                    "kp": float(entry.get("kill_participation", 0) or 0),
                    "win": 1.0 if entry.get("result") == "win" else 0.0,
                    "before_mmr": int(entry.get("before_mmr", 0) or 0),
                    "opponent_mmr": int(entry.get("opponent_mmr", 0) or 0),
                    "award": 1.0 if uid in (mvp_uid, ace_uid) else 0.0,
                })

        users = {}
        role_pool = {role: [] for role in ROLES}
        for uid, samples in per_user.items():
            samples = samples[-USER_SEARCH_RECENT_GAMES:]
            if len(samples) < USER_SEARCH_MIN_GAMES:
                continue
            user_info = ensure_user_format(guild_data.get(uid, {}))
            role_metrics = {}
            for role in ROLES:
                metric = _build_role_metric(user_info, role, samples)
                if metric:
                    role_metrics[role] = metric
                    role_pool[role].append({"uid": uid, **metric})
            if role_metrics:
                users[uid] = {
                    "uid": uid,
                    "info": user_info,
                    "games": len(samples),
                    "role_metrics": role_metrics,
                }

        rows = []
        for uid, user_row in users.items():
            scored_roles = {}
            for role, metric in user_row["role_metrics"].items():
                # The comparison population is intentionally strict: same position
                # and within one major-tier width (±400 MMR). Do not fall back to
                # unrelated roles just to manufacture confidence.
                peers = [
                    p for p in role_pool.get(role, [])
                    if p["uid"] != uid
                    and p["mmr"] > 0
                    and metric["mmr"] > 0
                    and abs(p["mmr"] - metric["mmr"]) <= 400
                ]
                scored_roles[role] = _score_role_vs_peers(metric, peers)

            if not scored_roles:
                continue
            focus_role = max(
                scored_roles,
                key=lambda r: (
                    scored_roles[r]["anomaly"],
                    scored_roles[r]["peer_count"],
                    scored_roles[r]["games"],
                ),
            )
            focus = scored_roles[focus_role]
            rows.append({
                **user_row,
                "focus_role": focus_role,
                "focus": focus,
                "anomaly": focus["anomaly"],
                "gap": focus["gap"],
                "expected_mmr": focus["expected_mmr"],
                "peer_count": focus["peer_count"],
                "scored_roles": scored_roles,
            })
        return rows
    def format_user_search_level(score):
        score = float(score or 0)
        if score >= 85:
            return "🔴 매우 높음"
        if score >= 72:
            return "🟠 높음"
        if score >= 60:
            return "🟡 관찰 필요"
        return "🟢 정상 범위"
    def _metric_advantage_line(label, value, peer_value, suffix="", digits=1):
        value = float(value or 0)
        peer_value = float(peer_value or 0)
        if digits == 0:
            value_text = f"{value:.0f}"
            peer_text = f"{peer_value:.0f}"
        else:
            value_text = f"{value:.{digits}f}"
            peer_text = f"{peer_value:.{digits}f}"
        if peer_value > 0:
            pct = ((value / peer_value) - 1.0) * 100
            delta = f" **{pct:+.0f}%**"
        else:
            delta = ""
        return f"{label} **{value_text}{suffix}** · 비교군 {peer_text}{suffix}{delta}"
    benchmark_position_choices = [
        app_commands.Choice(name="자동 (표본이 가장 많은 포지션)", value="AUTO"),
        app_commands.Choice(name="탑", value="TOP"),
        app_commands.Choice(name="정글", value="JUNGLE"),
        app_commands.Choice(name="미드", value="MID"),
        app_commands.Choice(name="원딜", value="ADC"),
        app_commands.Choice(name="서폿", value="SUPPORT"),
    ]

    @bot.tree.command(name="챔피언분석테스트", description="[관리자/테스트] 일반 유저 데이터에서 챔피언의 티어별 지표를 비교합니다.")
    @app_commands.choices(포지션=benchmark_position_choices)
    @app_commands.describe(챔피언="챔피언 이름 (예: 쉬바나, Shyvana)", 포지션="생략하면 표본이 가장 많은 포지션을 자동 선택합니다.")
    async def champion_analysis_test_command(
        interaction: discord.Interaction,
        챔피언: str,
        포지션: app_commands.Choice[str] | None = None,
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not psycopg or not DATABASE_URL:
            return await interaction.followup.send(
                "⚠️ PostgreSQL 연결을 사용할 수 없습니다. `DATABASE_URL`과 psycopg 설치 상태를 확인해주세요.",
                ephemeral=True,
            )

        try:
            report = benchmark.query_champion_tier_report(
                psycopg,
                DATABASE_URL,
                champion_query=챔피언,
                position=(포지션.value if 포지션 else "AUTO"),
                region="KR",
            )
        except Exception:
            logger.exception("챔피언분석테스트 벤치마크 조회 실패")
            return await interaction.followup.send(
                "⚠️ 벤치마크 DB 조회 중 오류가 발생했습니다. Render 로그를 확인해주세요.",
                ephemeral=True,
            )

        if not report:
            return await interaction.followup.send(
                f"⚠️ `{챔피언}`의 현재 패치 벤치마크 표본을 찾지 못했습니다. 아직 수집되지 않았거나 이름을 확인해주세요.",
                ephemeral=True,
            )

        embed = benchmark.build_champion_test_embed(discord, report)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(name="유저탐색", description="[관리자] 동티어대 같은 포지션 대비 특이점/저평가 유저를 깊게 분석합니다.")
    @app_commands.choices(작업=user_search_action_choices)
    @app_commands.describe(페이지="순위 선택 (1~10, 한 페이지에 한 명)")
    async def user_search_command(interaction: discord.Interaction, 작업: app_commands.Choice[str], 페이지: app_commands.Range[int, 1, 10] = 1):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        rows = build_user_search_rows(interaction.guild, gid)
        if not rows:
            return await interaction.followup.send(
                f"⚠️ 비교 가능한 상세 ROFL 기록이 없습니다. 유저당 최소 {USER_SEARCH_MIN_GAMES}경기, 포지션별 최소 {USER_SEARCH_MIN_ROLE_GAMES}경기가 필요합니다.",
                ephemeral=True,
            )

        action = 작업.value
        if action == "특이점":
            rows.sort(key=lambda r: (r["anomaly"], r["peer_count"], r["games"]), reverse=True)
            title = "🚨 특이점 유저 탐색"
        else:
            rows.sort(key=lambda r: (r["gap"], r["anomaly"], r["peer_count"], r["games"]), reverse=True)
            title = "📈 저평가 유저 탐색"

        idx = 페이지 - 1
        if idx >= len(rows) or idx >= 10:
            return await interaction.followup.send(
                f"⚠️ 현재 확인 가능한 순위는 1~{min(10, len(rows))}위입니다.",
                ephemeral=True,
            )

        row = rows[idx]
        focus = row["focus"]
        name = compact_riot_name(row["info"].get("lol_name", "")) or get_lineup_display_name(interaction.guild, gid, row["uid"])
        current_tier = get_tier_rank_label(focus["mmr"]).replace("다이아몬드", "다이아")
        expected_tier = get_tier_rank_label(focus["expected_mmr"]).replace("다이아몬드", "다이아")

        if action == "특이점":
            headline = f"특이점 **{focus['anomaly']:.0f}/100** · {format_user_search_level(focus['anomaly'])}"
        else:
            headline = f"보정 추정 괴리 **+{focus['gap']} MMR** · {current_tier} → **{expected_tier}**"

        embed = discord.Embed(
            title=f"{title} · #{페이지} {discord.utils.escape_markdown(str(name))}",
            description=(
                f"{headline}\n"
                f"핵심 포지션 **{focus['role']}** · 현재 **{focus['mmr']} ({current_tier})** · "
                f"해당 포지션 최근 **{focus['games']}경기**\n"
                f"동티어대 동일 포지션 비교군 **{focus['peer_count']}명**"
            ),
            color=0x2b2d31,
        )
        if focus["peer_count"] >= USER_SEARCH_HIGH_CONFIDENCE_PEERS:
            embed.description += "\n✅ **비교 신뢰도 높음**"

        peer = focus.get("peer", {})
        metric_lines = [
            _metric_advantage_line("Impact", focus["score"], peer.get("score", 0), digits=1),
            _metric_advantage_line("DPM", focus["dpm"], peer.get("dpm", 0), digits=0),
            _metric_advantage_line("KDA", focus["kda"], peer.get("kda", 0), digits=1),
            _metric_advantage_line("킬 관여율", focus["kp"], peer.get("kp", 0), suffix="%", digits=0),
            _metric_advantage_line("승률", focus["winrate"], peer.get("winrate", 0), suffix="%", digits=0),
            _metric_advantage_line("MVP/ACE 비율", focus["award_rate"], peer.get("award_rate", 0), suffix="%", digits=0),
            f"상대 라인 MMR 평균차 **{focus['lane_gap']:+.0f}**",
        ]
        embed.add_field(
            name=f"🔎 {focus['role']}에서 무엇이 튀는가",
            value="\n".join(metric_lines),
            inline=False,
        )

        other_roles = []
        for role in ROLES:
            if role == row["focus_role"] or role not in row["scored_roles"]:
                continue
            data = row["scored_roles"][role]
            role_tier = get_tier_rank_label(data["mmr"]).replace("다이아몬드", "다이아")
            extra = " · ✅ 신뢰도 높음" if data["peer_count"] >= USER_SEARCH_HIGH_CONFIDENCE_PEERS else ""
            other_roles.append(
                f"**{role}** · 특이점 {data['anomaly']:.0f}/100 · {role_tier} · "
                f"{data['games']}경기 · 비교군 {data['peer_count']}명{extra}"
            )
        if other_roles:
            embed.add_field(
                name="🧭 다른 포지션은?",
                value="\n".join(other_roles),
                inline=False,
            )

        embed.set_footer(
            text="비교군 10명 이상일 때만 높은 신뢰도로 표시합니다. 적은 비교군의 MMR 추정치는 자동 축소 보정됩니다."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    async def test_title_grant_notice(interaction: discord.Interaction, 칭호: str):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)

        gid = str(interaction.guild_id)
        title = resolve_defined_title(칭호)
        if not title:
            return await interaction.response.send_message("⚠️ 테스트할 칭호를 입력해주세요.", ephemeral=True)

        condition_text = format_title_condition_block(gid, title)
        source_text = format_title_source_note_line(title)
        if is_first_limited_title(title):
            embed = discord.Embed(
                title="🌟 서버 최초 한정 칭호 획득!",
                description=(
                    f"{interaction.user.mention} 님이 서버에서 최초로 조건을 달성했습니다.\n\n"
                    f"획득 칭호\n**[{title}]**{source_text}\n\n"
                    f"{condition_text}"
                    "이 칭호는 **최초 달성자만 보유할 수 있습니다.**\n"
                    "`/칭호 작업:목록`에서 확인하고 `/칭호 작업:장착`으로 장착해보세요."
                ),
                color=0xf1c40f
            )
        else:
            embed = discord.Embed(
                title="🏷️ 퀘스트 달성!",
                description=(
                    f"{interaction.user.mention} 님이 새로운 칭호를 획득했습니다.\n\n"
                    f"획득 칭호\n**[{title}]**{source_text}\n\n"
                    f"{condition_text}"
                    "`/칭호 작업:목록`에서 확인하고 `/칭호 작업:장착`으로 장착해보세요."
                ),
                color=0x9b59b6
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @bot.tree.command(name="칭호관리", description="[관리자] 칭호 확인, 지급, 회수, 초기화, 테스트를 합니다.")
    @app_commands.choices(작업=[
        app_commands.Choice(name="보유확인", value="보유확인"),
        app_commands.Choice(name="지급", value="지급"),
        app_commands.Choice(name="회수", value="회수"),
        app_commands.Choice(name="초기화", value="초기화"),
        app_commands.Choice(name="테스트", value="테스트"),
        app_commands.Choice(name="대기열정리", value="대기열정리"),
    ])
    @app_commands.autocomplete(칭호=defined_title_autocomplete)
    async def admin_title_manage(
        interaction: discord.Interaction,
        작업: app_commands.Choice[str],
        유저: discord.Member = None,
        칭호: str = "",
        설명: str = "",
        카운트초기화: bool = True,
        전체확인: str = "",
    ):
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "titles"):
            return await interaction.response.send_message(get_disabled_feature_message("titles"), ephemeral=True)
        action = 작업.value
        if action == "보유확인":
            if not 유저:
                return await interaction.response.send_message("⚠️ 보유확인 대상 유저를 지정해주세요.", ephemeral=True)
            return await admin_title_list(interaction, 유저)
        if action == "지급":
            if not 유저 or not 칭호.strip():
                return await interaction.response.send_message("⚠️ 지급 대상 유저와 칭호를 입력해주세요.", ephemeral=True)
            return await admin_grant_title(interaction, 유저, 칭호, 설명)
        if action == "회수":
            if not 유저 or not 칭호.strip():
                return await interaction.response.send_message("⚠️ 회수 대상 유저와 칭호를 입력해주세요.", ephemeral=True)
            return await admin_revoke_title(interaction, 유저, 칭호)
        if action == "초기화":
            if not 유저:
                return await interaction.response.send_message("⚠️ 초기화 대상 유저를 지정해주세요.", ephemeral=True)
            return await admin_reset_titles(interaction, 유저)
        if action == "테스트":
            if not 칭호.strip():
                return await interaction.response.send_message("⚠️ 테스트할 칭호를 입력해주세요.", ephemeral=True)
            return await test_title_grant_notice(interaction, 칭호)
        if action == "대기열정리":
            return await admin_clear_queue_lineup_titles(interaction, 유저, 카운트초기화, 전체확인)
        return await interaction.response.send_message("⚠️ 알 수 없는 칭호관리 작업입니다.", ephemeral=True)
    async def equip_title(interaction: discord.Interaction, 칭호: str):
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "titles"):
            return await interaction.response.send_message(get_disabled_feature_message("titles"), ephemeral=True)
        uid = str(interaction.user.id)
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 소환사 정보가 등록되어 있지 않습니다.", ephemeral=True)

        user_info = ensure_user_format(bot.user_data[gid][uid])
        owned_titles = user_info["titles"].get("owned", [])
        title = 칭호.strip()
        if title not in owned_titles:
            truncated_matches = [owned for owned in owned_titles if str(owned)[:100] == title]
            if len(truncated_matches) == 1:
                title = truncated_matches[0]
        if title not in owned_titles:
            return await interaction.response.send_message("⚠️ 보유 중인 칭호만 장착할 수 있습니다. `/칭호 작업:목록`을 확인해주세요.", ephemeral=True)

        user_info["titles"]["equipped"] = title
        bot.save_lucid_data(gid)
        await interaction.response.send_message(f"✅ 칭호 **[{title}]** 을(를) 장착했습니다.")
    async def unequip_title(interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "titles"):
            return await interaction.response.send_message(get_disabled_feature_message("titles"), ephemeral=True)
        uid = str(interaction.user.id)
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 소환사 정보가 등록되어 있지 않습니다.", ephemeral=True)

        user_info = ensure_user_format(bot.user_data[gid][uid])
        user_info["titles"]["equipped"] = None
        bot.save_lucid_data(gid)
        await interaction.response.send_message("✅ 장착 중인 칭호를 해제했습니다.")
    async def setup_title_channel(interaction: discord.Interaction, 채널: discord.TextChannel):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)

        gid = str(interaction.guild_id)
        get_title_system(gid)["channel_id"] = str(채널.id)
        bot.save_lucid_data(gid)
        await interaction.response.send_message(f"✅ 칭호 알림 채널을 {채널.mention}(으)로 설정했습니다.", ephemeral=True)
    async def admin_grant_title(interaction: discord.Interaction, 유저: discord.Member, 칭호: str, 설명: str = ""):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)

        gid = str(interaction.guild_id)
        uid = str(유저.id)
        bot.user_data.setdefault(gid, {})
        if uid not in bot.user_data[gid]:
            bot.user_data[gid][uid] = make_default_user(유저.display_name)

        title = 칭호.strip()
        if not title:
            return await interaction.response.send_message("⚠️ 지급할 칭호를 입력해주세요.", ephemeral=True)

        condition = (설명 or "").strip()
        if condition:
            get_title_system(gid).setdefault("custom_conditions", {})[title] = condition

        added = add_title_to_user(gid, uid, title)
        bot.save_lucid_data(gid)

        condition_text = f"\n└ `{condition}`" if condition else ""
        if added:
            notice_embed = discord.Embed(
                title="🏷️ 새로운 칭호가 지급되었습니다!",
                description=(
                    f"{유저.mention} 님에게 새로운 칭호가 지급되었습니다.\n\n"
                    f"지급 칭호\n**[{title}]**"
                    + (f"\n\n지급 사유\n`{condition}`" if condition else "")
                    + "\n\n`/칭호 작업:목록`에서 확인하고 `/칭호 작업:장착`으로 장착할 수 있습니다."
                ),
                color=0x9b59b6
            )
            await interaction.response.send_message(
                content=유저.mention,
                embed=notice_embed
            )
        else:
            if condition:
                await interaction.response.send_message(f"⚠️ {유저.mention} 님은 이미 칭호 **[{title}]** 을(를) 보유 중입니다.\n설명은 업데이트했습니다.{condition_text}", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ {유저.mention} 님은 이미 칭호 **[{title}]** 을(를) 보유 중입니다.", ephemeral=True)
    async def admin_revoke_title(interaction: discord.Interaction, 유저: discord.Member, 칭호: str):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)

        gid = str(interaction.guild_id)
        uid = str(유저.id)
        user_data = bot.user_data.get(gid, {}).get(uid)
        if not user_data:
            return await interaction.response.send_message("⚠️ 해당 유저의 소환사 정보가 없습니다.", ephemeral=True)

        user_info = ensure_user_format(user_data)
        title = 칭호.strip()
        owned = user_info["titles"].get("owned", [])
        if title not in owned:
            return await interaction.response.send_message(f"⚠️ {유저.mention} 님은 칭호 **[{title}]** 을(를) 보유하고 있지 않습니다.", ephemeral=True)

        owned.remove(title)
        for bucket in user_info["titles"].get("seasons", {}).values():
            if isinstance(bucket, dict) and title in bucket.get("owned", []):
                bucket["owned"] = [item for item in bucket.get("owned", []) if item != title]
        if user_info["titles"].get("equipped") == title:
            user_info["titles"]["equipped"] = None
        bot.save_lucid_data(gid)
        await interaction.response.send_message(f"✅ {유저.mention} 님의 칭호 **[{title}]** 을(를) 회수했습니다.", ephemeral=True)
    async def admin_clear_queue_lineup_titles(
        interaction: discord.Interaction,
        유저: discord.Member = None,
        카운트초기화: bool = True,
        전체확인: str = ""
    ):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)

        gid = str(interaction.guild_id)
        guild_data = bot.user_data.setdefault(gid, {})

        if 유저 is None and 전체확인.strip() != "전체":
            return await interaction.response.send_message(
                "⚠️ 전체 유저를 정리하려면 `전체확인`에 `전체`를 입력해주세요.\n"
                "특정 유저만 정리하려면 `유저` 옵션을 지정하면 됩니다.",
                ephemeral=True
            )

        targets = []
        if 유저 is not None:
            uid = str(유저.id)
            user_data = guild_data.get(uid)
            if not user_data:
                return await interaction.response.send_message("⚠️ 해당 유저의 소환사 정보가 없습니다.", ephemeral=True)
            targets.append((uid, user_data))
        else:
            targets = list(iter_user_records(guild_data))

        touched_users = 0
        removed_count = 0
        for _uid, user_data in targets:
            removed = clear_queue_lineup_titles(user_data, reset_counts=카운트초기화)
            if removed or 카운트초기화:
                touched_users += 1
                removed_count += len(removed)

        bot.save_lucid_data(gid)

        scope_text = 유저.mention if 유저 else f"전체 유저 {len(targets)}명"
        count_text = "카운트도 0으로 초기화했습니다." if 카운트초기화 else "카운트는 유지했습니다."
        await interaction.response.send_message(
            f"✅ {scope_text} 대상 대기열 칭호 정리 완료\n"
            f"회수한 칭호: **{removed_count}개** / 처리 대상: **{touched_users}명**\n"
            f"{count_text}",
            ephemeral=True
        )
    async def admin_reset_titles(interaction: discord.Interaction, 유저: discord.Member):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 운영 권한이 부족합니다.", ephemeral=True)

        gid = str(interaction.guild_id)
        uid = str(유저.id)
        user_data = bot.user_data.get(gid, {}).get(uid)
        if not user_data:
            return await interaction.response.send_message("⚠️ 해당 유저의 소환사 정보가 없습니다.", ephemeral=True)

        user_info = ensure_user_format(user_data)
        user_info["titles"] = {
            "owned": [],
            "equipped": None,
            "pending_dynasty": None,
            "pending_custom": [],
            "achieved_custom": [],
            "seasons": {
                TITLE_LEGACY_SEASON: {"owned": [], "achieved_custom": []},
                TITLE_CURRENT_SEASON: {"owned": [], "achieved_custom": []},
            },
            "_season_v2_migrated": True,
        }
        bot.save_lucid_data(gid)
        await interaction.response.send_message(f"✅ {유저.mention} 님의 칭호 데이터를 초기화했습니다.", ephemeral=True)
    async def league_record(interaction: discord.Interaction, 유저: discord.Member = None):
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "league"):
            return await interaction.response.send_message(get_disabled_feature_message("league"), ephemeral=True)
        target = 유저 or interaction.user
        data = bot.user_data.get(gid, {}).get(str(target.id))
        if not data:
            return await interaction.response.send_message("⚠️ 소환사 정보가 등록되어 있지 않습니다.", ephemeral=True)

        user_data = ensure_user_format(data)
        embed = discord.Embed(title=f"🏆 {target.display_name} 님의 리그전 전적", color=0x9b59b6)

        def add_mode_field(title, stats):
            participations = int(stats.get("participations", 0) or 0)
            wins = int(stats.get("wins", 0) or 0)
            runner_ups = int(stats.get("runner_ups", 0) or 0)
            third_places = int(stats.get("third_places", 0) or 0)
            match_wins = int(stats.get("match_win", 0) or 0)
            match_losses = int(stats.get("match_loss", 0) or 0)
            match_total = match_wins + match_losses
            match_wr = (match_wins / match_total * 100) if match_total else 0.0
            medal_line = format_league_medal_line(wins, runner_ups, third_places) or "입상 기록 없음"
            embed.add_field(
                name=title,
                value=(
                    f"참가 **{participations}회** · {medal_line}\n"
                    f"매치 **{match_total}전 {match_wins}승 {match_losses}패** · 승률 **{match_wr:.1f}%**"
                ),
                inline=False,
            )

        add_mode_field("🗺️ 협곡 리그전", user_data.get("league_stats", {}) or {})
        add_mode_field("❄️ 칼바람 리그전", user_data.get("aram_league_stats", {}) or {})
        embed.set_footer(text="MVP/ACE는 각 매치에 ROFL 상세 기록이 저장된 경우 전체 MVP/ACE 기록에 합산됩니다.")
        await interaction.response.send_message(embed=embed)
    async def league_help(interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "league"):
            return await interaction.response.send_message(get_disabled_feature_message("league"), ephemeral=True)
        embed = discord.Embed(
            title="🏆 리그전 도움말",
            description="협곡/칼바람 리그전은 **15~40명(3~8팀)**으로 진행하며 일반 큐 MMR은 변동하지 않습니다.",
            color=0x9b59b6,
        )
        embed.add_field(
            name="🗺️ 협곡 리그전",
            value=(
                "5명씩 팀을 구성하며 포지션을 배정합니다.\n"
                "일반 라인 MMR을 기준으로 팀 밸런스를 맞춥니다."
            ),
            inline=False,
        )
        embed.add_field(
            name="❄️ 칼바람 리그전",
            value=(
                "5명씩 팀을 구성하며 **라인 배정은 없습니다.**\n"
                "각 유저의 일반 큐 라인 MMR 중 **현재 최고 MMR**을 기준으로 팀 밸런스를 맞춥니다."
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 경기 기록",
            value=(
                "매치 승/패와 리그전 입상 기록은 자동 누적됩니다.\n"
                "각 매치 ROFL을 `/리플레이기록`으로 저장하면 KDA·상세스탯과 **MVP/ACE**도 계산됩니다.\n"
                "`/리그전전적 [@유저]`에서 협곡/칼바람 리그전 기록을 함께 확인할 수 있습니다."
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)
    @bot.tree.command(name="우승기록", description="협곡 리그전 최근 우승팀 또는 특정 회차 우승팀을 확인합니다.")
    async def league_champion_record(interaction: discord.Interaction, 회차: app_commands.Range[int, 1, 999] = None):
        gid = str(interaction.guild_id)
        if not is_feature_enabled(gid, "league"):
            return await interaction.response.send_message(get_disabled_feature_message("league"), ephemeral=True)
        records = get_league_champions(gid)
        if not records:
            return await interaction.response.send_message(f"🏆 아직 기록된 {LEAGUE_MODE_NAME} 우승팀이 없습니다.", ephemeral=True)

        if 회차 is None:
            record = records[-1]
        else:
            record = next((item for item in records if int(item.get("round", 0)) == 회차), None)
            if not record:
                return await interaction.response.send_message(f"⚠️ {LEAGUE_MODE_NAME} {회차}회차 우승 기록을 찾을 수 없습니다.", ephemeral=True)

        winner = record.get("winner", {})
        runner_up = record.get("runner_up", {})
        third_place = record.get("third_place", {}) or {}
        round_no = record.get("round", "?")

        winner_team = {
            "team_no": winner.get("team_no"),
            "name": winner.get("name") or f"{round_no}회차 우승팀",
            "players": winner.get("players", []),
            "roles": winner.get("roles", {}),
        }
        runner_team = {
            "team_no": runner_up.get("team_no"),
            "name": runner_up.get("name") or f"{round_no}회차 준우승팀",
            "players": runner_up.get("players", []),
            "roles": runner_up.get("roles", {}),
        }
        third_team = {
            "team_no": third_place.get("team_no"),
            "name": third_place.get("name") or f"{round_no}회차 3등",
            "players": third_place.get("players", []),
            "roles": third_place.get("roles", {}),
        }

        embed = discord.Embed(
            title=f"🏆 {LEAGUE_MODE_NAME} {round_no}회차 우승 기록",
            description=f"**{discord.utils.escape_markdown(winner_team['name'])}**\n\n축하드립니다!",
            color=0xf1c40f
        )
        embed.add_field(
            name=format_league_result_field_name("🥇", "우승팀", winner_team),
            value=format_league_role_lines(interaction.guild, gid, winner_team),
            inline=False
        )
        embed.add_field(
            name=format_league_result_field_name("🥈", "준우승팀", runner_team),
            value=format_league_role_lines(interaction.guild, gid, runner_team),
            inline=False
        )
        if third_place:
            embed.add_field(
                name=format_league_result_field_name("🥉", "3등", third_team),
                value=format_league_role_lines(interaction.guild, gid, third_team),
                inline=False
            )
        if record.get("time"):
            embed.set_footer(text=f"기록일: {record['time']}")
        await interaction.response.send_message(embed=embed)
    @bot.tree.command(name="라이벌", description="본인 또는 다른 유저의 현재 대표 라이벌과 상대전적을 확인합니다.")
    async def rival_stats(
        interaction: discord.Interaction,
        유저: discord.Member = None,
    ):
        gid = str(interaction.guild_id)
        target = 유저 or interaction.user
        target_uid = str(target.id)
        if target_uid not in bot.user_data.get(gid, {}):
            return await interaction.response.send_message(
                f"⚠️ {target.display_name} 님은 등록된 소환사가 아닙니다.",
                ephemeral=True,
            )

        refresh_auto_rivals(interaction.guild, gid, [target_uid])
        target_info = ensure_user_format(bot.user_data[gid][target_uid])
        rival_uid = get_custom_rival_uid(gid, target_uid)

        if not rival_uid:
            embed = discord.Embed(
                title=f"⚔️ {target.display_name} 님의 라이벌",
                description="아직 공식 라이벌이 없습니다.",
                color=0xe67e22,
            )
            return await interaction.response.send_message(embed=embed)

        summary = get_rival_head_to_head_summary(gid, target_uid, rival_uid)
        score = calculate_rival_score(summary)
        rival_name = compact_riot_name(get_registered_display_name(interaction.guild, gid, rival_uid)) or get_registered_display_name(interaction.guild, gid, rival_uid)
        target_name = compact_riot_name(get_registered_display_name(interaction.guild, gid, target_uid)) or get_registered_display_name(interaction.guild, gid, target_uid)

        # Recent five head-to-head results from the target's perspective.
        recent_results = []
        same_lane = 0
        for record in reversed(get_match_history(gid)):
            if record.get("cancelled"):
                continue
            players = record.get("players", []) or []
            player = next((p for p in players if str(p.get("user_id")) == target_uid), None)
            rival = next((p for p in players if str(p.get("user_id")) == rival_uid), None)
            if not player or not rival or player.get("team") == rival.get("team"):
                continue
            if player.get("role") in ROLES and player.get("role") == rival.get("role"):
                same_lane += 1
            if len(recent_results) < 5 and player.get("result") in ("win", "loss"):
                recent_results.append("승" if player.get("result") == "win" else "패")

        lead = summary["wins"] - summary["losses"]
        if lead > 0:
            edge_text = f"{target_name} +{lead}승"
        elif lead < 0:
            edge_text = f"{rival_name} +{abs(lead)}승"
        else:
            edge_text = "동률"

        embed = discord.Embed(
            title=f"⚔️ {target.display_name} 님의 대표 라이벌",
            description=(
                f"**{discord.utils.escape_markdown(str(target_name))} VS {discord.utils.escape_markdown(str(rival_name))}**\n\n"
                f"맞대결 **{summary['games']}전 {summary['wins']}승 {summary['losses']}패**\n"
                f"승률 **{calc_win_rate(summary):.1f}% : {100.0-calc_win_rate(summary):.1f}%**"
            ),
            color=0xe67e22,
        )
        embed.add_field(
            name="최근 맞대결",
            value=" · ".join(recent_results) if recent_results else "기록 없음",
            inline=True,
        )
        embed.add_field(name="현재 우세", value=discord.utils.escape_markdown(str(edge_text)), inline=True)
        embed.add_field(name="동일 라인 맞대결", value=f"{same_lane}경기", inline=True)
        await interaction.response.send_message(embed=embed)
    @bot.tree.command(name="리그전전적", description="본인 또는 다른 유저의 협곡/칼바람 리그전 기록을 확인합니다.")
    async def tournament_record(interaction: discord.Interaction, 유저: discord.Member = None):
        return await league_record(interaction, 유저)
    async def send_matchup_fit(interaction: discord.Interaction, 유저: discord.Member = None, mode: str = "good"):
        gid = str(interaction.guild_id)
        target = 유저 or interaction.user
        _, opponent_stats = get_relation_stats(gid, str(target.id))
        candidates = [(uid, stats) for uid, stats in opponent_stats.items() if stats['games'] >= 5]

        if not candidates:
            return await interaction.response.send_message(
                f"📉 **{target.display_name}** 님이 상대로 5회 이상 만난 기록이 아직 부족합니다.",
                ephemeral=True
            )

        if mode == "bad":
            uid, stats = min(
                candidates,
                key=lambda item: (calc_win_rate(item[1]), item[1]['wins'], -item[1]['games'])
            )
            title = f"🧊 {target.display_name} 님의 나쁜상성"
            field_name = "상대로 승률이 가장 낮은 소환사"
            color = 0xe74c3c
        else:
            uid, stats = max(
                candidates,
                key=lambda item: (calc_win_rate(item[1]), item[1]['wins'], item[1]['games'])
            )
            title = f"🌿 {target.display_name} 님의 좋은상성"
            field_name = "상대로 승률이 가장 높은 소환사"
            color = 0x2ecc71

        embed = discord.Embed(
            title=title,
            color=color
        )
        embed.add_field(name=field_name, value=get_member_label(interaction.guild, gid, uid), inline=False)
        embed.add_field(
            name="상대전적",
            value=f"**{stats['games']}전 {stats['wins']}승 {stats['losses']}패** · 승률 **{calc_win_rate(stats):.1f}%**",
            inline=False
        )
        await interaction.response.send_message(embed=embed)
    @bot.tree.command(name="상성", description="두 유저의 상대전적과 같은 팀 기록을 확인합니다.")
    async def matchup_stats(interaction: discord.Interaction, 유저1: discord.Member, 유저2: discord.Member):
        gid = str(interaction.guild_id)
        duo_stats, opponent_stats = get_relation_stats(gid, str(유저1.id))
        opponent = opponent_stats.get(str(유저2.id), {'games': 0, 'wins': 0, 'losses': 0})
        duo = duo_stats.get(str(유저2.id), {'games': 0, 'wins': 0, 'losses': 0})

        embed = discord.Embed(
            title=f"⚔️ {유저1.display_name} vs {유저2.display_name} 상성표",
            color=0x3498db
        )
        embed.add_field(
            name="상대전적",
            value=(
                f"{유저1.mention} 기준 **{opponent['games']}전 {opponent['wins']}승 {opponent['losses']}패**\n"
                f"승률 **{calc_win_rate(opponent):.1f}%**"
            ),
            inline=False
        )
        embed.add_field(
            name="같은 팀 시너지",
            value=(
                f"같은 팀 **{duo['games']}전 {duo['wins']}승 {duo['losses']}패**\n"
                f"승률 **{calc_win_rate(duo):.1f}%**"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=embed)
    def format_match_balance_snapshot(record):
        if record.get("mode", "classic") not in ("classic", LOW_TIER_MODE_KEY, NOBAN_MODE_KEY, LEAGUE_MODE_KEY, LEAGUE_SERIES_MODE_KEY):
            return None

        by_team_role = {}
        for player in record.get("players", []):
            team = player.get("team")
            role = player.get("role")
            if team not in ("blue", "red") or role not in ROLES:
                continue
            score = player.get("lineup_mmr", player.get("before_mmr"))
            try:
                by_team_role[(team, role)] = int(score)
            except (TypeError, ValueError):
                continue

        blue_scores = [by_team_role.get(("blue", role)) for role in ROLES]
        red_scores = [by_team_role.get(("red", role)) for role in ROLES]
        if any(score is None for score in blue_scores + red_scores):
            return None

        blue_avg = int(sum(blue_scores) / len(ROLES))
        red_avg = int(sum(red_scores) / len(ROLES))
        avg_gap = blue_avg - red_avg

        blue_tier = get_tier_rank_label(blue_avg).replace("다이아몬드", "다이아")
        red_tier = get_tier_rank_label(red_avg).replace("다이아몬드", "다이아")
        blue_emoji = get_tier_emoji(get_tier_name(blue_avg))
        red_emoji = get_tier_emoji(get_tier_name(red_avg))

        if abs(avg_gap) < 50:
            balance_text = "⚪ 거의 균형"
        elif avg_gap > 0:
            balance_text = "🔵 BLUE 근소 우세" if avg_gap < 150 else "🔵 BLUE 우세"
        else:
            balance_text = "🔴 RED 근소 우세" if abs(avg_gap) < 150 else "🔴 RED 우세"

        return (
            f"BLUE {blue_emoji} **{blue_tier}** · RED {red_emoji} **{red_tier}**\n"
            f"{balance_text}"
        )
    def build_match_history_detail_embed(guild, gid, record):
        match_id = record.get("id")
        guild_data = bot.user_data.setdefault(gid, {})
        awards = match_stats.score_match_awards(guild_data, match_id) if match_id else {}
        scores = list(awards.get("scores") or [])

        embed = discord.Embed(
            title="📊 경기 상세 스탯",
            description="DPM · AI Score",
            color=0x3498db,
        )
        if not scores:
            embed.description = "📭 이 경기에는 아직 ROFL 상세 스탯이 없습니다."
            return embed

        score_by_uid = {str(row.get("user_id")): row for row in scores}
        role_order = {role: idx for idx, role in enumerate(ROLES)}

        for team_index, team_name in enumerate(("blue", "red")):
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

            lines = []
            for player in team_players:
                uid = str(player.get("user_id"))
                detail = get_match_detail_entry(guild_data, match_id, uid) or {}
                score = score_by_uid.get(uid, {})
                role = str(detail.get("role") or player.get("role") or "라인")
                champion = str(detail.get("champion") or score.get("champion") or "챔피언 미입력")
                name = compact_riot_name(get_registered_display_name(guild, gid, uid))

                champion_marker = get_champion_display_marker(champion, guild, gid)
                if champion_marker != champion and champion_marker.startswith("<"):
                    champion_display = champion_marker.split(" ", 1)[0]
                else:
                    champion_display = champion

                dpm = safe_detail_float(detail.get("dpm", score.get("dpm", 0)))
                ai = score.get("display_score", score.get("expectation_score", score.get("score")))
                try:
                    ai_text = str(int(round(float(ai))))
                except (TypeError, ValueError):
                    ai_text = "-"

                lines.append(
                    f"**{role}** · {champion_display} · **{discord.utils.escape_markdown(name)}**\n"
                    f"　DPM **{dpm:.0f}** · AI Score `{ai_text}`"
                )

            field_name = "🔵 BLUE TEAM" if team_name == "blue" else "🔴 RED TEAM"
            if record.get("mode") in (LEAGUE_SERIES_MODE_KEY, ARAM_LEAGUE_MODE_KEY):
                teams = record.get("teams", []) or []
                team = teams[team_index] if len(teams) > team_index else {}
                team_label = str(team.get("name") or "").strip()
                if not team.get("side"):
                    field_name = team_label or field_name
                elif team_label:
                    field_name += f" · {team_label}"
            embed.add_field(
                name=field_name,
                value="\n\n".join(lines) if lines else "기록 없음",
                inline=False,
            )

        return embed
    class MatchHistoryStatsView(discord.ui.View):
        def __init__(self, guild, gid, record):
            super().__init__(timeout=900)
            self.guild = guild
            self.gid = gid
            self.record = record
            match_id = str(record.get("id") or "")
            detail_store = match_stats.get_store(bot.user_data.setdefault(gid, {}))
            if not match_id or not detail_store.get(match_id):
                self.detail_button.disabled = True
                self.detail_button.label = "📊 상세 스탯 없음"

        @discord.ui.button(label="📊 상세 스탯", style=discord.ButtonStyle.secondary)
        async def detail_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            embed = build_match_history_detail_embed(self.guild, self.gid, self.record)
            await interaction.response.send_message(embed=embed, ephemeral=True)
    @bot.tree.command(name="경기기록", description="최근 경기 기록을 확인합니다. 유저를 지정하면 개인 최근 경기를 봅니다.")
    @app_commands.choices(라인=[app_commands.Choice(name=r, value=r) for r in ROLES])
    async def match_history_command(
        interaction: discord.Interaction,
        순번: app_commands.Range[int, 1, 50] = 1,
        유저: discord.Member = None,
        라인: app_commands.Choice[str] = None,
        페이지: app_commands.Range[int, 1, 50] = 1,
    ):
        # 경기기록 조립 과정에서 상세 ROFL/MVP 데이터를 읽느라 3초를 넘길 수 있으므로
        # Discord interaction을 먼저 승인하고 결과는 followup으로 전송한다.
        await interaction.response.defer()
        gid = str(interaction.guild_id)

        if 유저:
            role_name = 라인.value if 라인 else None
            entries = get_user_match_records(gid, 유저.id, role=role_name)
            if not entries:
                role_text = f" [{role_name}]" if role_name else ""
                return await interaction.followup.send(
                    f"📭 **{유저.display_name}** 님의{role_text} 경기 기록이 없습니다.",
                    ephemeral=True
                )
            embed = build_user_match_history_embed(gid, 유저, entries, page=페이지, page_size=5, role=role_name)
            return await interaction.followup.send(embed=embed)

        records = sorted(get_valid_match_history(gid), key=parse_history_time, reverse=True)

        if len(records) < 순번:
            return await interaction.followup.send(
                f"📜 확인 가능한 경기 기록이 {len(records)}개뿐입니다.",
                ephemeral=True
            )

        record = records[순번 - 1]
        if record.get('mode') == EVENT_MODE_KEY:
            mode_name = EVENT_MODE_NAME
        elif record.get('mode') == ARAM_MODE_KEY:
            mode_name = ARAM_MODE_NAME
        elif record.get('mode') == LEAGUE_MODE_KEY:
            mode_name = LEAGUE_MODE_NAME
        elif record.get('mode') == LEAGUE_SERIES_MODE_KEY:
            mode_name = LEAGUE_SERIES_MODE_NAME
        elif record.get('mode') == ARAM_LEAGUE_MODE_KEY:
            mode_name = ARAM_LEAGUE_MODE_NAME
        elif record.get('mode') == LOW_TIER_MODE_KEY:
            mode_name = LOW_TIER_MODE_NAME
        elif record.get('mode') == NOBAN_MODE_KEY:
            mode_name = NOBAN_MODE_NAME
        else:
            mode_name = "공식 내전"
        winner = str(record.get('winner', '기록 없음') or '기록 없음')
        winner_label = f"{winner.upper()} TEAM" if winner in ("blue", "red") else winner
        duration_suffix = format_history_duration_suffix(gid, record)
        embed = discord.Embed(
            title=f"📜 최근 {순번}번째 경기 기록 · {mode_name}",
            description=(
                f"**{record.get('time', '시간 없음')}**{duration_suffix} · **{winner_label} 승리**"
            ),
            color=0x95a5a6
        )


        lines = format_match_record_lines(interaction.guild, gid, record)
        for idx, line in enumerate(lines, 1):
            series_team = None
            if record.get('mode') in (LEAGUE_SERIES_MODE_KEY, ARAM_LEAGUE_MODE_KEY):
                teams = record.get("teams", []) or []
                series_team = teams[idx - 1] if len(teams) >= idx else {}
                side = series_team.get("side")
                side_label = "🔵 BLUE TEAM" if side == "blue" else "🔴 RED TEAM" if side == "red" else ""
                team_label = str(series_team.get("name") or f"{idx}팀")
                field_name = f"{side_label} · {team_label}" if side_label else team_label
                if record.get("winner") == team_label:
                    field_name += " 🏆"
            elif record.get('mode') == EVENT_MODE_KEY:
                field_name = f"팀 정보 {idx}"
            else:
                team_key = "blue" if idx == 1 else "red"
                field_name = "🔵 BLUE TEAM" if idx == 1 else "🔴 RED TEAM"
                if record.get("winner") == team_key:
                    field_name += " 🏆"
            embed.add_field(name=field_name, value=line, inline=False)

        view = MatchHistoryStatsView(interaction.guild, gid, record)
        await interaction.followup.send(embed=embed, view=view)
    async def delete_summoner_profile_by_uid(interaction, gid, uid):
        user_info = ensure_user_format(bot.user_data[gid][uid])
        deleted_name = user_info.get("lol_name", uid)
        deleted_mmr = dict(user_info.get("mmr", {}))
        deleted_plays = dict(user_info.get("plays", {}))
        del bot.user_data[gid][uid]

        removed_queue_entries = 0
        for queue_key, entries in ensure_guild_queues(gid).items():
            filtered, removed = remove_uid_from_queue_entries(entries, uid)
            if removed:
                ensure_guild_queues(gid)[queue_key] = filtered
                removed_queue_entries += removed

        bot.save_lucid_data(gid)
        if interaction.guild:
            await update_ranking_board(interaction.guild, gid)

        mmr_text = " / ".join(f"{role} {deleted_mmr.get(role, 0)}점 {deleted_plays.get(role, 0)}판" for role in ROLES)
        embed = discord.Embed(
            title="🗑️ 소환사 데이터 삭제 완료",
            description=f"`{deleted_name}` (`{uid}`) 프로필 데이터를 삭제했습니다.",
            color=0xe74c3c
        )
        embed.add_field(name="삭제 전 라인 정보", value=mmr_text or "기록 없음", inline=False)
        embed.add_field(name="대기열 제거", value=f"{removed_queue_entries}건", inline=True)
        embed.set_footer(text="경기 히스토리는 기록 보존을 위해 삭제하지 않습니다.")
        return embed
    def format_summoner_search_line(guild, gid, uid):
        user_info = ensure_user_format(bot.user_data.get(gid, {}).get(str(uid), {}))
        member = guild.get_member(int(uid)) if guild else None
        lol_name = user_info.get("lol_name", "이름 없음")
        display_name = member.display_name if member else "탈퇴/미접속"
        avg_mmr = get_avg_mmr(user_info.get("mmr", {}))
        total_games = int(user_info.get("win", 0) or 0) + int(user_info.get("loss", 0) or 0)
        return f"• `{uid}` · **{lol_name}** · {display_name} · 평균 {avg_mmr}점 · {total_games}전"
    def has_assigned_mmr_record(user_info):
        mmr_values = user_info.get("mmr", {}) or {}
        play_values = user_info.get("plays", {}) or {}
        if any(int(score or 0) != 0 for score in mmr_values.values()):
            return True
        if int(user_info.get("noban_mmr", 0) or 0) != 0:
            return True
        return any(int(count or 0) > 0 for count in play_values.values())
    async def find_departed_summoner_profiles(guild, gid, limit=25):
        if not guild:
            return []

        departed = []
        for uid, data in iter_user_records(bot.user_data.get(gid, {})):
            user_info = ensure_user_format(data)
            if not has_assigned_mmr_record(user_info):
                continue

            try:
                uid_int = int(uid)
            except (TypeError, ValueError):
                continue

            if guild.get_member(uid_int):
                continue

            try:
                await guild.fetch_member(uid_int)
                continue
            except discord.NotFound:
                pass
            except (discord.Forbidden, discord.HTTPException):
                pass

            avg_mmr = get_avg_mmr(user_info.get("mmr", {}))
            total_games = int(user_info.get("win", 0) or 0) + int(user_info.get("loss", 0) or 0)
            departed.append((avg_mmr, total_games, str(uid), user_info))

        departed.sort(key=lambda item: (item[1], item[0]), reverse=True)
        return departed[:limit]
    title_action_choices = [
        app_commands.Choice(name="목록", value="list"),
        app_commands.Choice(name="장착", value="equip"),
        app_commands.Choice(name="해제", value="unequip"),
    ]
    title_season_choices = [
        app_commands.Choice(name="전체", value="all"),
        app_commands.Choice(name="시즌1", value=TITLE_LEGACY_SEASON),
        app_commands.Choice(name="시즌2", value=TITLE_CURRENT_SEASON),
    ]
    @bot.tree.command(name="칭호", description="시즌별 칭호 목록 확인과 장착/해제를 관리합니다.")
    @app_commands.choices(작업=title_action_choices, 시즌=title_season_choices)
    @app_commands.autocomplete(칭호=owned_title_autocomplete)
    async def unified_title(interaction: discord.Interaction, 작업: app_commands.Choice[str], 시즌: app_commands.Choice[str]=None, 칭호: str=""):
        if 작업.value == "list":
            return await title_list(interaction, 시즌.value if 시즌 else "all")
        if 작업.value == "equip":
            if not 칭호.strip():
                return await interaction.response.send_message("⚠️ 장착할 칭호를 선택해주세요.", ephemeral=True)
            return await equip_title(interaction, 칭호)
        if 작업.value == "unequip":
            return await unequip_title(interaction)
    @bot.tree.command(name="시너지", description="5판 이상 기록 기준으로 최고의 듀오와 좋은/나쁜 상대를 함께 확인합니다.")
    async def unified_synergy(interaction: discord.Interaction, 유저: discord.Member=None):
        gid=str(interaction.guild_id)
        target=유저 or interaction.user
        duo_stats, opponent_stats=get_relation_stats(gid,str(target.id))

        def _is_current_guild_member(uid: str) -> bool:
            try:
                return interaction.guild is not None and interaction.guild.get_member(int(uid)) is not None
            except (TypeError, ValueError):
                return False

        # 시너지 리포트는 현재 서버에 남아 있는 멤버만 노출한다.
        # 탈퇴한 유저의 과거 전적 데이터는 보존하지만 추천/상성 후보에서는 제외한다.
        duos=[(uid,s) for uid,s in duo_stats.items() if s['games']>=5 and _is_current_guild_member(uid)]
        opps=[(uid,s) for uid,s in opponent_stats.items() if s['games']>=5 and _is_current_guild_member(uid)]
        embed=discord.Embed(title=f"🤝 {target.display_name} 시너지 리포트",color=0x2ecc71)
        if duos:
            uid,s=max(duos,key=lambda item:(calc_win_rate(item[1]),item[1]['wins'],item[1]['games']))
            embed.add_field(name="🤝 같은 팀 최고 승률",value=f"{get_member_label(interaction.guild,gid,uid)}\n**{s['games']}전 {s['wins']}승 {s['losses']}패 · {calc_win_rate(s):.1f}%**",inline=False)
        else:
            embed.add_field(name="🤝 같은 팀 최고 승률",value="5판 이상 함께한 기록 없음",inline=False)
        if opps:
            good_uid,good=max(opps,key=lambda item:(calc_win_rate(item[1]),item[1]['wins'],item[1]['games']))
            bad_uid,bad=min(opps,key=lambda item:(calc_win_rate(item[1]),item[1]['wins'],-item[1]['games']))
            embed.add_field(name="🌿 상대 승률 최고",value=f"{get_member_label(interaction.guild,gid,good_uid)} · **{good['games']}전 {good['wins']}승 {good['losses']}패 · {calc_win_rate(good):.1f}%**",inline=False)
            embed.add_field(name="🧊 상대 승률 최저",value=f"{get_member_label(interaction.guild,gid,bad_uid)} · **{bad['games']}전 {bad['wins']}승 {bad['losses']}패 · {calc_win_rate(bad):.1f}%**",inline=False)
        else:
            embed.add_field(name="⚔️ 상대 상성",value="5판 이상 상대한 기록 없음",inline=False)
        embed.set_footer(text="모든 항목은 최소 5판 이상 기록만 집계합니다.")
        await interaction.response.send_message(embed=embed)
    class SummonerChangeModal(discord.ui.Modal, title="소환사 Riot ID 변경"):
        riot_id = discord.ui.TextInput(
            label="소환사명#태그",
            placeholder="예: Hide on bush#KR1",
            required=True,
            max_length=80,
        )

        def __init__(self, target: discord.Member):
            super().__init__()
            self.target = target

        async def on_submit(self, interaction: discord.Interaction):
            new_name = normalize_riot_id(str(self.riot_id.value or "").strip())
            if not new_name:
                return await interaction.response.send_message(
                    "⚠️ Riot ID를 `닉네임#태그` 형식으로 입력해주세요.",
                    ephemeral=True,
                )

            gid = str(interaction.guild_id)
            uid = str(self.target.id)
            if gid not in bot.user_data or uid not in bot.user_data[gid]:
                return await interaction.response.send_message(
                    "⚠️ 등록되지 않은 소환사입니다. 신규 등록은 `/소환사등록`을 사용해주세요.",
                    ephemeral=True,
                )

            if self.target.id != interaction.user.id and not is_match_admin(interaction):
                return await interaction.response.send_message("🚫 다른 유저의 Riot ID는 내전 관리자만 변경할 수 있습니다.", ephemeral=True)

            await interaction.response.defer(ephemeral=True, thinking=True)
            user_info = ensure_user_format(bot.user_data[gid][uid])
            old_name = str(user_info.get("lol_name") or self.target.display_name)

            owner_uid, owner_name, is_alt = find_lol_account_owner(gid, new_name, exclude_uid=uid)
            if owner_uid:
                owner_member = interaction.guild.get_member(int(owner_uid)) if interaction.guild else None
                owner_label = owner_member.mention if owner_member else f"UID {owner_uid}"
                kind = "부계정" if is_alt else "본계정"
                return await interaction.followup.send(
                    f"⚠️ `{owner_name}` 은(는) 이미 {owner_label} 님의 {kind}으로 등록되어 있습니다.",
                    ephemeral=True,
                )

            user_info["lol_name"] = new_name
            bot.user_data[gid][uid] = user_info
            bot.save_lucid_data(gid)
            nickname_status = await set_member_nickname(self.target, new_name)

            embed = discord.Embed(
                title="🔄 소환사 Riot ID 변경 완료",
                description=(
                    f"대상: {self.target.mention}\n이전: **{old_name}**\n변경: **{new_name}**"
                    f"{nickname_status}"
                ),
                color=0x3498db,
            )
            embed.set_footer(text="전적/MMR 등 기존 데이터는 그대로 유지됩니다.")
            await interaction.followup.send(embed=embed, ephemeral=True)
    class AltSummonerRegisterModal(discord.ui.Modal, title="부계정 등록"):
        riot_id = discord.ui.TextInput(
            label="부계정 소환사명#태그",
            placeholder="예: LucidSub#KR1",
            required=True,
            max_length=80,
        )

        def __init__(self, target: discord.Member):
            super().__init__()
            self.target = target

        async def on_submit(self, interaction: discord.Interaction):
            alt_name = normalize_riot_id(str(self.riot_id.value or "").strip())
            if not alt_name:
                return await interaction.response.send_message("⚠️ `닉네임#태그` 형식의 Riot ID를 입력해주세요.", ephemeral=True)
            await register_alt_summoner(interaction, self.target, alt_name)
    class AltSummonerDeleteSelect(discord.ui.Select):
        def __init__(self, target: discord.Member, alt_names: list[str]):
            self.target = target
            options = [discord.SelectOption(label=name[:100], value=name) for name in alt_names[:25]]
            super().__init__(placeholder="삭제할 부계정을 선택하세요", min_values=1, max_values=1, options=options)

        async def callback(self, interaction: discord.Interaction):
            await delete_alt_summoner(interaction, self.target, self.values[0])
            self.view.stop()
    class AltSummonerDeleteView(discord.ui.View):
        def __init__(self, target: discord.Member, alt_names: list[str]):
            super().__init__(timeout=900)
            self.add_item(AltSummonerDeleteSelect(target, alt_names))
    class AltSummonerManageView(discord.ui.View):
        def __init__(self, target: discord.Member):
            super().__init__(timeout=900)
            self.target = target

        @discord.ui.button(label="부계정 등록", style=discord.ButtonStyle.success, emoji="➕")
        async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not is_match_admin(interaction):
                return await interaction.response.send_message("🚫 부계정 관리는 내전 관리자만 사용할 수 있습니다.", ephemeral=True)
            await interaction.response.send_modal(AltSummonerRegisterModal(self.target))

        @discord.ui.button(label="부계정 삭제", style=discord.ButtonStyle.danger, emoji="🗑️")
        async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not is_match_admin(interaction):
                return await interaction.response.send_message("🚫 부계정 관리는 내전 관리자만 사용할 수 있습니다.", ephemeral=True)
            gid = str(interaction.guild_id)
            user_info = ensure_user_format(bot.user_data.get(gid, {}).get(str(self.target.id), {}))
            alt_names = list(user_info.get("alt_lol_names", []) or [])
            if not alt_names:
                return await interaction.response.send_message("📭 삭제할 부계정이 없습니다.", ephemeral=True)
            await interaction.response.send_message(
                f"🗑️ **{self.target.display_name}** 님에게서 삭제할 부계정을 선택해주세요.",
                view=AltSummonerDeleteView(self.target, alt_names),
                ephemeral=True,
            )
    class SummonerDeleteConfirmView(discord.ui.View):
        def __init__(self, uid: str):
            super().__init__(timeout=120)
            self.uid = str(uid)

        @discord.ui.button(label="정말 삭제", style=discord.ButtonStyle.danger, emoji="🗑️")
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not interaction.user.guild_permissions.administrator:
                return await interaction.response.send_message("🚫 디스코드 서버 관리자만 데이터를 삭제할 수 있습니다.", ephemeral=True)
            gid = str(interaction.guild_id)
            if self.uid not in bot.user_data.get(gid, {}):
                return await interaction.response.send_message("⚠️ 이미 삭제되었거나 존재하지 않는 소환사 데이터입니다.", ephemeral=True)
            operation_key = bot.begin_admin_operation(gid, f"delete_user:{self.uid}")
            if not operation_key:
                return await reject_duplicate_admin_operation(interaction, f"{self.uid} 데이터 삭제")
            try:
                await interaction.response.defer(ephemeral=True)
                embed = await delete_summoner_profile_by_uid(interaction, gid, self.uid)
                for item in self.children:
                    item.disabled = True
                await interaction.followup.send(embed=embed, ephemeral=True)
                self.stop()
            finally:
                bot.finish_admin_operation(operation_key)

        @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(content="삭제를 취소했습니다.", embed=None, view=self)
            self.stop()
    class DepartedSummonerDeleteSelect(discord.ui.Select):
        def __init__(self, departed):
            options = []
            for avg_mmr, total_games, uid, user_info in departed[:25]:
                lol_name = str(user_info.get("lol_name") or f"UID {uid}")
                options.append(discord.SelectOption(
                    label=lol_name[:100],
                    value=str(uid),
                    description=f"{total_games}전 · 평균 {avg_mmr}점 · UID {uid}"[:100],
                ))
            super().__init__(placeholder="삭제할 탈퇴/미접속 소환사를 선택하세요", min_values=1, max_values=1, options=options)

        async def callback(self, interaction: discord.Interaction):
            uid = str(self.values[0])
            gid = str(interaction.guild_id)
            user_info = ensure_user_format(bot.user_data.get(gid, {}).get(uid, {}))
            embed = build_summoner_delete_preview(interaction.guild, gid, uid, user_info)
            await interaction.response.send_message(embed=embed, view=SummonerDeleteConfirmView(uid), ephemeral=True)
    class DepartedSummonerDeleteView(discord.ui.View):
        def __init__(self, departed):
            super().__init__(timeout=900)
            self.add_item(DepartedSummonerDeleteSelect(departed))
    def build_summoner_delete_preview(guild, gid, uid, user_info):
        member = guild.get_member(int(uid)) if guild else None
        lol_name = str(user_info.get("lol_name") or "이름 없음")
        avg_mmr = get_avg_mmr(user_info.get("mmr", {}))
        games = int(user_info.get("win", 0) or 0) + int(user_info.get("loss", 0) or 0)
        alt_count = len(user_info.get("alt_lol_names", []) or [])
        target_label = member.mention if member else f"UID `{uid}`"
        embed = discord.Embed(
            title="⚠️ 소환사 데이터 완전 삭제 확인",
            description=(
                f"대상: {target_label}\n"
                f"Riot ID: **{lol_name}**\n"
                f"전적: **{games}전** · 평균 MMR **{avg_mmr}점**\n"
                f"부계정: **{alt_count}개**\n\n"
                "이 작업은 소환사 프로필/MMR/배치/승패/칭호/부계정 등 현재 유저 데이터를 삭제합니다."
            ),
            color=0xe74c3c,
        )
        embed.set_footer(text="경기 히스토리는 기록 보존을 위해 별도로 유지됩니다.")
        return embed
    summoner_manage_group = app_commands.Group(
        name="소환사관리",
        description="소환사 정보, Riot ID, 부계정과 데이터를 관리합니다.",
    )
    @summoner_manage_group.command(name="정보", description="내 소환사 정보 또는 운영진이 선택한 유저의 정보를 확인합니다.")
    @app_commands.describe(유저="조회할 유저. 비우면 본인 정보를 표시합니다.")
    async def summoner_manage_info(interaction: discord.Interaction, 유저: discord.Member = None):
        target = 유저 or interaction.user
        if target.id != interaction.user.id and not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 다른 유저 정보는 내전 관리자만 조회할 수 있습니다.", ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(target.id)
        if gid not in bot.user_data or uid not in bot.user_data[gid]:
            return await interaction.response.send_message("⚠️ 등록된 소환사 정보가 없습니다.", ephemeral=True)
        user_info = ensure_user_format(bot.user_data[gid][uid])
        embed = build_my_info_embed(interaction.guild, gid, uid, user_info, target)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @summoner_manage_group.command(name="변경", description="등록된 Riot ID를 변경합니다. 입력은 팝업 창에서 진행합니다.")
    @app_commands.describe(유저="변경할 유저. 비우면 본인 Riot ID를 변경합니다.")
    async def summoner_manage_change(interaction: discord.Interaction, 유저: discord.Member = None):
        target = 유저 or interaction.user
        if target.id != interaction.user.id and not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 다른 유저의 Riot ID는 내전 관리자만 변경할 수 있습니다.", ephemeral=True)
        gid = str(interaction.guild_id)
        if str(target.id) not in bot.user_data.get(gid, {}):
            return await interaction.response.send_message("⚠️ 등록되지 않은 소환사입니다. 신규 등록은 `/소환사등록`을 사용해주세요.", ephemeral=True)
        await interaction.response.send_modal(SummonerChangeModal(target))
    @summoner_manage_group.command(name="부계정", description="부계정 목록을 확인하고 버튼으로 등록/삭제합니다.")
    @app_commands.describe(유저="부계정을 관리할 유저. 내전 관리자 전용입니다.")
    async def summoner_manage_alt(interaction: discord.Interaction, 유저: discord.Member = None):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 부계정 관리는 내전 관리자만 사용할 수 있습니다.", ephemeral=True)
        target = 유저 or interaction.user
        gid = str(interaction.guild_id)
        uid = str(target.id)
        if uid not in bot.user_data.get(gid, {}):
            return await interaction.response.send_message("⚠️ 대상 유저는 먼저 `/소환사등록`이 필요합니다.", ephemeral=True)
        user_info = ensure_user_format(bot.user_data[gid][uid])
        alt_names = list(user_info.get("alt_lol_names", []) or [])
        alt_list = "\n".join(f"• `{name}`" for name in alt_names) if alt_names else "등록된 부계정 없음"
        embed = discord.Embed(
            title="🎮 부계정 관리",
            description=f"대상: {target.mention}\n본계정: `{user_info.get('lol_name', target.display_name)}`",
            color=0x3498db,
        )
        embed.add_field(name="등록된 부계정", value=alt_list, inline=False)
        embed.set_footer(text="아래 버튼에서 등록 또는 삭제할 수 있습니다.")
        await interaction.response.send_message(embed=embed, view=AltSummonerManageView(target), ephemeral=True)
    @summoner_manage_group.command(name="임시배치설정", description="[내전 관리자] 임시배치를 특정 라인 또는 전체 라인에 설정합니다.")
    @app_commands.describe(유저="임시배치로 전환할 유저", 라인="임시배치를 적용할 라인. 비우면 전체 라인")
    @app_commands.choices(라인=PROVISIONAL_ROLE_CHOICES)
    async def summoner_manage_provisional_on(interaction: discord.Interaction, 유저: discord.Member, 라인: str = PROVISIONAL_ALL_ROLES_VALUE):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 내전 관리자만 사용할 수 있습니다.", ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(유저.id)
        if uid not in bot.user_data.get(gid, {}):
            return await interaction.response.send_message("⚠️ 대상 유저는 먼저 `/소환사등록`이 필요합니다.", ephemeral=True)

        target_role = _normalize_provisional_role(라인)
        if str(라인 or PROVISIONAL_ALL_ROLES_VALUE) != PROVISIONAL_ALL_ROLES_VALUE and target_role is None:
            return await interaction.response.send_message("⚠️ 올바른 라인을 선택해주세요.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        user_info = ensure_user_format(bot.user_data[gid][uid])
        set_provisional_mmr_state(
            user_info, active=True, actor_id=interaction.user.id, reset_games=True, role=target_role
        )
        config = get_provisional_mmr_config(gid)
        bot.save_lucid_data(gid)
        label = target_role or "전체 라인"
        await interaction.followup.send(
            f"🟡 {유저.mention} 님의 **{label}**에 임시배치를 설정했습니다.\n"
            f"해당 라인으로 플레이한 일반 내전만 **{config['games']}경기 / 기본 ±{config['delta']}점**으로 집계됩니다.\n"
            "각 라인은 독립적으로 완료되며, 완료된 라인만 자동으로 정식 상태로 전환됩니다.",
            ephemeral=True,
        )
    @summoner_manage_group.command(name="임시배치해제", description="[내전 관리자] 특정 라인 또는 전체 라인의 임시배치를 해제합니다.")
    @app_commands.describe(유저="임시배치를 해제할 유저", 라인="해제할 라인. 비우면 전체 라인")
    @app_commands.choices(라인=PROVISIONAL_ROLE_CHOICES)
    async def summoner_manage_provisional_off(interaction: discord.Interaction, 유저: discord.Member, 라인: str = PROVISIONAL_ALL_ROLES_VALUE):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 내전 관리자만 사용할 수 있습니다.", ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(유저.id)
        if uid not in bot.user_data.get(gid, {}):
            return await interaction.response.send_message("⚠️ 등록된 소환사 정보가 없습니다.", ephemeral=True)

        target_role = _normalize_provisional_role(라인)
        if str(라인 or PROVISIONAL_ALL_ROLES_VALUE) != PROVISIONAL_ALL_ROLES_VALUE and target_role is None:
            return await interaction.response.send_message("⚠️ 올바른 라인을 선택해주세요.", ephemeral=True)

        user_info = ensure_user_format(bot.user_data[gid][uid])
        state = get_provisional_mmr_state(user_info)
        target_roles = [target_role] if target_role else list(ROLES)
        active_targets = [role for role in target_roles if is_provisional_mmr_active(user_info, role)]
        if not active_targets:
            label = target_role or "전체 라인"
            return await interaction.response.send_message(
                f"ℹ️ {label}에 활성화된 임시배치가 없습니다.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        progress = []
        for role in active_targets:
            games = int(((state.get("role_states") or {}).get(role) or {}).get("games", 0) or 0)
            progress.append(f"{role} {games}경기")
        set_provisional_mmr_state(user_info, active=False, role=target_role)
        bot.save_lucid_data(gid)
        await interaction.followup.send(
            f"✅ {유저.mention} 님의 **{', '.join(active_targets)}** 임시배치를 해제했습니다.\n"
            f"진행도: {' · '.join(progress)}",
            ephemeral=True,
        )
    class ProvisionalStatusListView(discord.ui.View):
        PAGE_SIZE = 5

        def __init__(self, owner_id, guild, gid, entries, config):
            super().__init__(timeout=900)
            self.owner_id = int(owner_id)
            self.guild = guild
            self.gid = str(gid)
            self.entries = list(entries)
            self.config = dict(config)
            self.page = 0
            self._refresh_buttons()

        @property
        def page_count(self):
            return max(1, (len(self.entries) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

        def _refresh_buttons(self):
            self.prev_button.disabled = self.page <= 0
            self.next_button.disabled = self.page >= self.page_count - 1

        def build_embed(self):
            start = self.page * self.PAGE_SIZE
            page_entries = self.entries[start:start + self.PAGE_SIZE]
            if not page_entries:
                description = "현재 임시배치가 적용된 유저가 없습니다."
            else:
                lines = []
                for idx, entry in enumerate(page_entries, start=start + 1):
                    role_parts = []
                    for role, games in entry["roles"]:
                        role_parts.append(
                            f"{get_role_display_marker(role, self.guild)} **{role}** {games}/{self.config['games']}"
                        )
                    lines.append(f"**{idx}. {entry['name']}** - " + " · ".join(role_parts))
                description = "\n".join(lines)

            embed = discord.Embed(
                title="🟡 임시배치 유저 목록",
                description=description,
                color=0xF1C40F if self.entries else 0x95A5A6,
            )
            embed.set_footer(
                text=(
                    f"{self.page + 1}/{self.page_count} 페이지 · 총 {len(self.entries)}명 · "
                    f"라인별 {self.config['games']}경기 / 기본 ±{self.config['delta']}점"
                )
            )
            return embed

        async def interaction_check(self, interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("🚫 이 목록은 명령어를 실행한 관리자만 조작할 수 있습니다.", ephemeral=True)
                return False
            return True

        @discord.ui.button(label="이전", emoji="◀️", style=discord.ButtonStyle.secondary)
        async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.page > 0:
                self.page -= 1
            self._refresh_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

        @discord.ui.button(label="다음", emoji="▶️", style=discord.ButtonStyle.secondary)
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.page < self.page_count - 1:
                self.page += 1
            self._refresh_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
    @summoner_manage_group.command(name="임시배치확인", description="[내전 관리자] 현재 임시배치가 적용된 유저와 라인을 확인합니다.")
    async def summoner_manage_provisional_status(interaction: discord.Interaction):
        if not is_match_admin(interaction):
            return await interaction.response.send_message(
                "🚫 내전 관리자만 사용할 수 있습니다.",
                ephemeral=True,
            )

        gid = str(interaction.guild_id)
        config = get_provisional_mmr_config(gid)
        entries = []

        for uid, raw_info in bot.user_data.get(gid, {}).items():
            if not str(uid).isdigit() or not isinstance(raw_info, dict):
                continue
            user_info = ensure_user_format(raw_info)
            role_states = (get_provisional_mmr_state(user_info).get("role_states") or {})
            active_roles = []
            for role in ROLES:
                role_state = role_states.get(role) if isinstance(role_states.get(role), dict) else {}
                if not bool(role_state.get("active")):
                    continue
                games = int(role_state.get("games", 0) or 0)
                active_roles.append((role, min(games, int(config["games"]))))
            if not active_roles:
                continue

            member = interaction.guild.get_member(int(uid)) if interaction.guild else None
            riot_name = compact_riot_name(user_info.get("lol_name", ""))
            display_name = riot_name or (member.display_name if member else f"UID {uid}")
            entries.append({
                "uid": str(uid),
                "name": display_name,
                "roles": active_roles,
            })

        entries.sort(key=lambda item: item["name"].casefold())
        view = ProvisionalStatusListView(interaction.user.id, interaction.guild, gid, entries, config)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)
    @summoner_manage_group.command(name="임시배치초기화", description="[내전 관리자] 특정 라인 또는 전체 라인의 임시배치를 0경기로 다시 시작합니다.")
    @app_commands.describe(유저="임시배치를 다시 시작할 유저", 라인="초기화할 라인. 비우면 전체 라인")
    @app_commands.choices(라인=PROVISIONAL_ROLE_CHOICES)
    async def summoner_manage_provisional_reset(interaction: discord.Interaction, 유저: discord.Member, 라인: str = PROVISIONAL_ALL_ROLES_VALUE):
        if not is_match_admin(interaction):
            return await interaction.response.send_message("🚫 내전 관리자만 사용할 수 있습니다.", ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(유저.id)
        if uid not in bot.user_data.get(gid, {}):
            return await interaction.response.send_message("⚠️ 등록된 소환사 정보가 없습니다.", ephemeral=True)

        target_role = _normalize_provisional_role(라인)
        if str(라인 or PROVISIONAL_ALL_ROLES_VALUE) != PROVISIONAL_ALL_ROLES_VALUE and target_role is None:
            return await interaction.response.send_message("⚠️ 올바른 라인을 선택해주세요.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        user_info = ensure_user_format(bot.user_data[gid][uid])
        set_provisional_mmr_state(
            user_info, active=True, actor_id=interaction.user.id, reset_games=True, role=target_role
        )
        config = get_provisional_mmr_config(gid)
        bot.save_lucid_data(gid)
        label = target_role or "전체 라인"
        await interaction.followup.send(
            f"🔄 {유저.mention} 님의 **{label}** 임시배치를 **0/{config['games']}경기**로 다시 시작했습니다.\n"
            f"현재 서버 설정 기준 기본 변동폭은 **±{config['delta']}점**입니다.",
            ephemeral=True,
        )
    @summoner_manage_group.command(name="데이터삭제", description="소환사 데이터를 완전히 삭제합니다. 디스코드 서버 관리자 전용입니다.")
    @app_commands.describe(유저="삭제할 현재 서버 유저. 비우면 탈퇴/미접속 기록을 탐색합니다.")
    async def summoner_manage_delete(interaction: discord.Interaction, 유저: discord.Member = None):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("🚫 디스코드 서버 관리자만 데이터를 삭제할 수 있습니다.", ephemeral=True)
        gid = str(interaction.guild_id)
        if 유저 is not None:
            uid = str(유저.id)
            if uid not in bot.user_data.get(gid, {}):
                return await interaction.response.send_message("⚠️ 해당 유저의 소환사 데이터를 찾지 못했습니다.", ephemeral=True)
            user_info = ensure_user_format(bot.user_data[gid][uid])
            embed = build_summoner_delete_preview(interaction.guild, gid, uid, user_info)
            return await interaction.response.send_message(embed=embed, view=SummonerDeleteConfirmView(uid), ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        departed = await find_departed_summoner_profiles(interaction.guild, gid)
        if not departed:
            return await interaction.followup.send(
                "📭 삭제 후보인 탈퇴/미접속 소환사 기록을 찾지 못했습니다. 현재 서버 유저를 삭제하려면 `유저`를 선택해주세요.",
                ephemeral=True,
            )
        lines = []
        for avg_mmr, total_games, uid, user_info in departed[:25]:
            lines.append(f"• **{user_info.get('lol_name', '이름 없음')}** · {total_games}전 · 평균 {avg_mmr}점 · `{uid}`")
        embed = discord.Embed(
            title="🔎 삭제 가능한 탈퇴/미접속 소환사",
            description="\n".join(lines),
            color=0x95a5a6,
        )
        embed.set_footer(text="아래 선택창에서 대상을 고르면 최종 확인 화면이 열립니다.")
        await interaction.followup.send(embed=embed, view=DepartedSummonerDeleteView(departed), ephemeral=True)
    def format_streak_display(streak_val):
        """
        유저의 연승/연패 스탯을 프로필에 예쁘게 출력하기 위한 포맷 함수입니다.
        """
        if streak_val >= 2:
            return f"🔥 {streak_val}연승"
        elif streak_val <= -2:
            return f"🧊 {abs(streak_val)}연패"
        elif streak_val == 1:
            return "1연승"
        elif streak_val == -1:
            return "1연패"
        else:
            return "평범한 상태"
    def is_all_roles_placed(user_info):
        user_info = ensure_user_format(user_info)
        return all(user_info['plays'].get(role, 0) >= 10 for role in ROLES)
    def has_all_roles_games(user_info, games):
        user_info = ensure_user_format(user_info)
        return all(user_info['plays'].get(role, 0) >= games for role in ROLES)
    def has_challenger_average_with_all_roles(user_info):
        return is_all_roles_placed(user_info) and get_avg_mmr(user_info.get('mmr', {})) >= TITLE_MMR_CHALLENGER
    def get_breakthrough_500_role(user_info):
        user_info = ensure_user_format(user_info)
        for role in ROLES:
            current_mmr = int(user_info.get("mmr", {}).get(role, 0) or 0)
            initial_mmr = get_role_initial_mmr(user_info, role, current_mmr)
            if initial_mmr > 0 and current_mmr - initial_mmr >= TITLE_MMR_BREAKTHROUGH_GAP:
                return role
        return None
    def has_seven_down_eight_up(gid, uid):
        uid = str(uid)
        loss_streak = 0
        rebound_win_streak = 0
        rebound_ready = False

        for record in sorted(get_valid_match_history(gid), key=parse_history_time):
            if record.get("mode", "classic") != "classic":
                continue
            player = next((p for p in record.get("players", []) if str(p.get("user_id")) == uid), None)
            if not player:
                continue

            result = player.get("result")
            if result == "loss":
                loss_streak += 1
                rebound_ready = loss_streak >= 7
                rebound_win_streak = 0
            elif result == "win":
                if rebound_ready:
                    rebound_win_streak += 1
                    if rebound_win_streak >= 8:
                        return True
                else:
                    rebound_win_streak = 0
                loss_streak = 0
            else:
                loss_streak = 0
                rebound_win_streak = 0
                rebound_ready = False

        return False
    def get_role_winrate(user_info, role):
        stats = ensure_user_format(user_info)['role_stats'].get(role, {})
        wins = stats.get('win', 0)
        losses = stats.get('loss', 0)
        total = wins + losses
        return (wins / total * 100) if total else 0.0
    def get_event_counts(user_info):
        user_info = ensure_user_format(user_info)
        arena = user_info.get('event_stats', {}).get(EVENT_MODE_KEY, {})
        aram = user_info.get('event_stats', {}).get(ARAM_MODE_KEY, {})
        league = user_info.get('league_stats', {})
        return {
            "league_wins": league.get('wins', 0),
            "arena_wins": arena.get('win', 0),
            "aram_wins": aram.get('win', 0),
            "aram_losses": aram.get('loss', 0),
        }
    def get_total_event_wins(user_info):
        counts = get_event_counts(user_info)
        return counts["league_wins"] + counts["arena_wins"] + counts["aram_wins"]
    def get_aram_winrate(user_info):
        counts = get_event_counts(user_info)
        total = counts["aram_wins"] + counts["aram_losses"]
        return (counts["aram_wins"] / total * 100) if total else 0.0
    def get_low_tier_match_stats(gid, uid):
        uid = str(uid)
        records = sorted(
            (record for record in get_valid_match_history(gid) if record.get("mode") == LOW_TIER_MODE_KEY),
            key=parse_history_time
        )
        games = 0
        wins = 0
        losses = 0
        current_streak = 0

        for record in records:
            player = next((p for p in record.get("players", []) if str(p.get("user_id")) == uid), None)
            if not player:
                continue

            result = player.get("result")
            games += 1
            if result == "win":
                wins += 1
                current_streak += 1
            elif result == "loss":
                losses += 1
                current_streak = 0

        return {
            "games": games,
            "wins": wins,
            "losses": losses,
            "winrate": (wins / games * 100) if games else 0.0,
            "current_streak": current_streak,
        }
    async def check_low_tier_title_unlocks(interaction, gid, uid):
        stats = get_low_tier_match_stats(gid, uid)
        games = stats["games"]
        wins = stats["wins"]
        winrate = stats["winrate"]
        current_streak = stats["current_streak"]

        if games >= 5:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["low_tier_5_games"])
        if games >= 5 and wins >= 3:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["low_tier_3_games_2_wins"])
        if games >= 5 and winrate >= 70:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["low_tier_5_games_70_wr"])
        if games >= 10:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["low_tier_10_games"])
        if games >= 10 and winrate >= 65:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["low_tier_10_games_65_wr"])
        if wins >= 3:
            await grant_first_title(interaction, gid, uid, "first_low_tier_3_wins")
        if current_streak >= 4:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["low_tier_3_streak"])
            await set_pending_low_tier_rising_star_title(interaction, gid, uid)
    async def check_classic_title_unlocks(interaction, gid, uid):
        member = interaction.guild.get_member(int(uid)) if getattr(interaction, "guild", None) else None
        if member:
            sync_permission_titles_for_member(interaction.guild, gid, member)
        user_info = ensure_user_format(bot.user_data[gid][str(uid)])
        title_thresholds = get_title_thresholds(gid)
        total_games = user_info.get('win', 0) + user_info.get('loss', 0)
        underdog = user_info.get('underdog_stats', {})

        for role in ROLES:
            role_stats = user_info.get('role_stats', {}).get(role, {})
            if int(role_stats.get('win', 0) or 0) == 7 and int(role_stats.get('loss', 0) or 0) == 0:
                await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["perfect_start"])
                break

        if total_games >= title_thresholds["first_50_games"]:
            await grant_first_title(interaction, gid, uid, "first_50_games")
        if has_all_roles_games(user_info, title_thresholds["first_all_rounder_games"]):
            await grant_first_title(interaction, gid, uid, "first_all_rounder")
        if has_challenger_average_with_all_roles(user_info):
            await grant_first_title(interaction, gid, uid, "first_all_lane_challenger")
        if user_info.get('streak', 0) >= 10:
            await grant_first_title(interaction, gid, uid, "first_streak_10")
        if user_info.get('streak', 0) >= title_thresholds["streak_15"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["streak_15"])
        if user_info.get('streak', 0) >= title_thresholds["streak_20"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["streak_20"])
        if user_info.get('streak', 0) <= -7:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["loss_streak_7"])
        if has_seven_down_eight_up(gid, uid):
            await grant_first_title(interaction, gid, uid, "first_seven_down_eight_up")
        if get_breakthrough_500_role(user_info):
            await grant_first_title(interaction, gid, uid, "first_breakthrough_500")
        if is_all_roles_placed(user_info) and get_avg_mmr(user_info.get('mmr', {})) >= TITLE_MMR_GRANDMASTER:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["grandmaster"])
        if has_challenger_average_with_all_roles(user_info):
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["challenger"])
        if has_all_roles_games(user_info, title_thresholds["all_roles_20"]):
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["all_roles_20"])
        if has_all_roles_games(user_info, title_thresholds["all_roles_50"]):
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["all_roles_50"])
        if has_all_roles_games(user_info, title_thresholds["all_roles_20"]) and get_avg_mmr(user_info.get('mmr', {})) >= TITLE_MMR_ALL_ROLES_SKILLED:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["all_roles_20_master"])

        for role, first_key in FIRST_ROLE_CHALLENGER_TITLE_KEYS.items():
            if user_info.get('mmr', {}).get(role, 0) >= TITLE_MMR_CHALLENGER:
                await grant_first_title(interaction, gid, uid, first_key)

        for role, title in ROLE_MASTER_TITLES.items():
            role_games = user_info['plays'].get(role, 0)
            if role_games >= title_thresholds["role_master_games"] and get_role_winrate(user_info, role) >= 60:
                await grant_title(interaction, gid, uid, title)

        lane_deficit_games = underdog.get('lane_deficit_score_games', 0)
        lane_deficit_wins = underdog.get('lane_deficit_score_wins', 0)
        lane_deficit_wr = (lane_deficit_wins / lane_deficit_games * 100) if lane_deficit_games else 0.0

        if underdog.get('lane_deficit_cost_wins', 0) >= title_thresholds["lane_deficit_wins"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["cost_effective_model"])
        if underdog.get('lane_deficit_200_wins', 0) >= title_thresholds["lane_deficit_200_wins"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["underdog_hunter"])
        if underdog.get('team_deficit_150_wins', 0) >= title_thresholds["team_deficit_150_wins"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["disadvantage_taste"])
        if lane_deficit_games >= title_thresholds["lane_deficit_games_wr"] and lane_deficit_wr >= 60:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["score_is_extra"])
        if underdog.get('lane_deficit_300_wins', 0) >= title_thresholds["lane_deficit_300_wins"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["peak_confiscator"])

        if underdog.get('first_giant_slayer_wins_v2', 0) >= title_thresholds["first_giant_slayer_wins"]:
            await grant_first_title(interaction, gid, uid, "first_giant_slayer")
        first_uv_games = int(underdog.get('first_undervalued_games_v2', 0) or 0)
        first_uv_wins = int(underdog.get('first_undervalued_wins_v2', 0) or 0)
        first_uv_wr = (first_uv_wins / first_uv_games * 100) if first_uv_games else 0.0
        if first_uv_games >= title_thresholds["first_undervalued_games"] and first_uv_wr >= 60:
            await grant_first_title(interaction, gid, uid, "first_undervalued_icon")
        if underdog.get('first_team_deficit_wins_v2', 0) >= title_thresholds["team_deficit_150_wins"]:
            await grant_first_title(interaction, gid, uid, "first_disadvantage_carry")
    async def check_duo_title_unlocks(interaction, gid, uid):
        user_info = ensure_user_format(bot.user_data[gid][str(uid)])
        title_thresholds = get_title_thresholds(gid)
        for partner_uid, stats in user_info.get('duo_stats', {}).items():
            if stats.get('wins', 0) >= title_thresholds["duo_wins"]:
                await set_pending_duo_title(interaction, gid, uid, partner_uid)
                break
    async def check_arena_title_unlocks(interaction, gid, uid):
        user_info = ensure_user_format(bot.user_data[gid][str(uid)])
        title_thresholds = get_title_thresholds(gid)
        stats = user_info['event_stats'][EVENT_MODE_KEY]
        wins = stats.get('win', 0)
        if wins >= title_thresholds["arena_wins_3"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["arena_wins_3"])
        if wins >= title_thresholds["arena_wins_5"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["arena_wins_5"])
        if wins >= title_thresholds["arena_wins_10"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["arena_wins_10"])
        await check_event_combo_title_unlocks(interaction, gid, uid)
    async def check_aram_title_unlocks(interaction, gid, uid):
        user_info = ensure_user_format(bot.user_data[gid][str(uid)])
        title_thresholds = get_title_thresholds(gid)
        counts = get_event_counts(user_info)
        aram_wins = counts["aram_wins"]
        aram_total = aram_wins + counts["aram_losses"]
        aram_wr = get_aram_winrate(user_info)

        if aram_total >= title_thresholds["aram_10_games"]:
            await grant_first_title(interaction, gid, uid, "first_aram_10_games")
        if aram_wins >= title_thresholds["aram_10_wins"]:
            await grant_first_title(interaction, gid, uid, "first_aram_10_wins")
        if aram_total >= title_thresholds["aram_10_games"] and aram_wr >= 70:
            await grant_first_title(interaction, gid, uid, "first_aram_high_winrate")
        if aram_total >= title_thresholds["aram_15_games"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["aram_games_15"])
        if aram_wins >= title_thresholds["aram_10_wins"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["aram_wins_10"])
        if aram_total >= title_thresholds["aram_30_games"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["aram_games_30"])
        if aram_wins >= title_thresholds["aram_20_wins"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["aram_wins_20"])
        if aram_total >= title_thresholds["aram_15_games"] and aram_wr >= 70:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["aram_high_winrate"])
        await check_event_combo_title_unlocks(interaction, gid, uid)
    async def check_event_combo_title_unlocks(interaction, gid, uid):
        user_info = ensure_user_format(bot.user_data[gid][str(uid)])
        title_thresholds = get_title_thresholds(gid)
        counts = get_event_counts(user_info)
        total_event_wins = get_total_event_wins(user_info)

        if counts["league_wins"] >= 1 and counts["arena_wins"] >= 1:
            await grant_first_title(interaction, gid, uid, "first_double_crown")
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["event_double_crown"])
        if counts["league_wins"] >= 1 and counts["arena_wins"] >= 1 and counts["aram_wins"] >= title_thresholds["event_all_round_aram_wins"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["event_all_round_player"])
        if total_event_wins >= title_thresholds["event_legend_wins"]:
            await set_pending_legend_title(interaction, gid, uid)
        if total_event_wins >= title_thresholds["event_wins_20"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["event_wins_20"])
        if total_event_wins >= title_thresholds["event_wins_30"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["event_wins_30"])
        if total_event_wins >= title_thresholds["event_wins_50"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["event_wins_50"])
    async def check_league_title_unlocks(interaction, gid, uid):
        user_info = ensure_user_format(bot.user_data[gid][str(uid)])
        title_thresholds = get_title_thresholds(gid)
        stats = user_info['league_stats']
        wins = stats.get('wins', 0)
        runner_ups = stats.get('runner_ups', 0)
        finals = wins + runner_ups
        if wins >= title_thresholds["league_wins_3"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["league_wins_3"])
        if wins >= title_thresholds["league_wins_5"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["league_wins_5"])
        if runner_ups >= title_thresholds["league_runner_ups_3"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["league_runner_ups_3"])
        if finals >= title_thresholds["league_finals_5"]:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["league_finals_5"])
        if stats.get('runner_up_streak', 0) >= 2:
            await grant_title(interaction, gid, uid, GENERAL_TITLE_DEFS["league_runner_up_streak_2"])
        if stats.get('win_streak', 0) >= 3:
            await grant_first_title(interaction, gid, uid, "first_threepeat")
            await set_pending_dynasty_title(interaction, gid, uid)
        await check_event_combo_title_unlocks(interaction, gid, uid)
    def update_duo_stats_for_team(gid, team_ids, is_win):
        for uid in team_ids:
            if uid not in bot.user_data.get(gid, {}):
                continue
            user_info = ensure_user_format(bot.user_data[gid][uid])
            for partner_uid in team_ids:
                if partner_uid == uid:
                    continue
                stats = user_info['duo_stats'].setdefault(partner_uid, {'games': 0, 'wins': 0, 'losses': 0})
                stats['games'] += 1
                if is_win:
                    stats['wins'] += 1
                else:
                    stats['losses'] += 1
    async def streak_ranking(interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        if gid not in bot.user_data:
            return await interaction.response.send_message("🔥 아직 연승 랭킹에 표시할 데이터가 없습니다.", ephemeral=True)

        streak_users = []
        for uid, data in iter_public_user_records(interaction.guild, gid):
            user_info = ensure_user_format(data)
            streak = user_info.get('streak', 0)
            if streak > 0:
                streak_users.append((uid, streak))

        if not streak_users:
            return await interaction.response.send_message("🔥 현재 연승 중인 소환사가 없습니다.", ephemeral=True)

        streak_users.sort(key=lambda item: item[1], reverse=True)
        lines = [
            f"**{idx}위** {get_member_label(interaction.guild, gid, uid)} · **{streak}연승**"
            for idx, (uid, streak) in enumerate(streak_users[:10], 1)
        ]
        embed = discord.Embed(
            title="🔥 현재 연승 랭킹 TOP 10",
            description="\n".join(lines),
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed)
    bot.tree.add_command(summoner_manage_group)
    exported = locals().copy()
    exported.pop("runtime", None)
    return exported
