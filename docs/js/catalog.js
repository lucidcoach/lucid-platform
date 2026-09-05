export const categories = [
  { id: "league", label: "리그오브레전드" },
  { id: "valorant", label: "발로란트" },
  { id: "academy", label: "테스트" },
];

export const filterSets = {
  league: {
    type: [
      { id: "all", label: "전체" },
      { id: "value", label: "가성비 리플레이" },
      { id: "low", label: "입문/저티어" },
      { id: "high", label: "고티어/프로지망" },
      { id: "team", label: "팀게임/스크림" },
    ],
    segment: [
      { id: "all", label: "전체 라인" },
      { id: "top", label: "탑" },
      { id: "mid", label: "미드" },
      { id: "jungle", label: "정글" },
      { id: "adc", label: "원딜" },
      { id: "support", label: "서폿" },
    ],
  },
  valorant: {
    type: [
      { id: "all", label: "전체" },
      { id: "value", label: "가성비 리플레이" },
      { id: "low", label: "입문/저티어" },
      { id: "high", label: "고티어/프로지망" },
      { id: "team", label: "팀게임/스크림" },
    ],
    segment: [
      { id: "all", label: "전체 역할" },
      { id: "duelist", label: "타격대" },
      { id: "controller", label: "전략가" },
      { id: "initiator", label: "척후대" },
      { id: "sentinel", label: "감시자" },
      { id: "aim", label: "에임/피킹" },
    ],
  },
  academy: {
    type: [
      { id: "all", label: "전체" },
      { id: "entry", label: "입문" },
      { id: "curriculum", label: "커리큘럼" },
      { id: "branding", label: "브랜딩" },
    ],
    segment: [
      { id: "all", label: "전체 과정" },
      { id: "coach-basic", label: "기초 과정" },
      { id: "coach-advanced", label: "심화 과정" },
      { id: "operation", label: "운영/관리" },
    ],
  },
};

export const purposes = Object.values(filterSets).flatMap((set) => [...set.type, ...set.segment]).filter(
  (item, index, array) => item.id !== "all" && array.findIndex((candidate) => candidate.id === item.id) === index
);

export const adminLineOptions = {
  league: ["탑", "미드", "정글", "원딜", "서폿"],
  valorant: ["타격대", "척후대", "감시자", "전략가"],
  academy: ["기초 과정", "심화 과정", "운영/관리"],
};

export const adminFieldOptions = {
  league: ["운영", "라인전", "시야", "오브젝트", "팀게임", "고티어"],
  valorant: ["에임", "피킹", "엔트리", "스크림", "리플레이", "팀 피드백"],
  academy: ["코치 입문", "커리큘럼", "피드백", "브랜딩", "운영", "수강생 관리"],
};

export const priceUnits = {
  time: ["30분", "1시간", "1.5시간", "2시간"],
  game: ["1게임", "2게임", "3게임"],
};

export const badgeOptions = ["엠버서더", "최우수", "우수", "추천", "일반", "저티어 입문", "입문 추천", "리뷰 우수", "팀 피드백 가능"];

export const text = {
  navMarket: "코칭",
  navBookings: "예약 관리",
  navAdmin: "코치 관리",
  navUsers: "회원 관리",
  sideLabel: "예약 안내",
  sideCopy: "코치 목록에서 원하는 상품을 고르면 상세 정보와 강의 구매를 바로 진행할 수 있습니다.",
  heroEyebrow: "LUCID COACH",
  heroTitle: "코칭",
  metricCoachesLabel: "강의",
  metricBookingsLabel: "예약",
  metricRatingLabel: "평점",
  searchLabel: "검색",
  searchPlaceholder: "코치명, 라인, 챔피언, 강의명",
  bookingEyebrow: "관리자 화면",
  bookingTitle: "예약 신청 목록",
  clearBookingsBtn: "예약 새로고침",
  thStatus: "상태",
  thStudent: "수강생",
  thLesson: "강의",
  thTime: "희망 시간",
  thContact: "연락처",
  thMemo: "메모",
  adminEyebrow: "로컬 편집",
  adminTitle: "코치 관리",
  resetCoachesBtn: "4명 · 8강의로 초기화",
  labelCategory: "카테고리",
  labelName: "코치명",
  labelTagline: "한 줄 소개",
  labelPurpose: "분류",
  labelRoles: "전문 분야",
  labelPrice: "가격",
  labelImage: "이미지 경로",
  labelImagePosition: "이미지 위치",
  labelBadges: "배지",
  labelBio: "상세 설명",
  optLeague: "리그오브레전드",
  optValorant: "발로란트",
  optAcademy: "테스트",
  saveCoachBtn: "저장",
  newCoachBtn: "새 강의",
  deleteCoachBtn: "삭제",
  bookingContactLabel: "Riot ID / Discord",
  bookingTimeLabel: "희망 시간",
  bookingMemoLabel: "요청사항",
  bookingSubmitBtn: "강의 구매",
  featuredTitle: "추천 코칭 상품",
  featuredHint: "후기와 재예약률이 좋은 강의",
  expertTitle: "코칭 상품 찾기",
  expertHint: "라인, 티어, 팀게임 기준으로 골라보세요.",
};

export const samples = [
  { id: "coach-shineast", category: "league", name: "샤이니스트 코치", coachKey: "shineast", coachProfileName: "샤이니스트 코치", tier: "최우수", coachTier: "최우수", coachSummary: "프로팀 출신 · 모든 라인 피드백 · 팀게임 운영까지 가능", tagline: "프로팀식 운영, 라인전 교정, 팀게임 피드백까지 보는 고급 코칭", bio: "모든 라인과 팀게임을 프로팀 관점으로 점검합니다. 미니맵 시선, 턴 사용, 귀환 타이밍, 오더와 시야 컨트롤처럼 승패를 가르는 선택을 리플레이로 정리합니다.", purpose: ["value", "team", "high", "mid"], roles: ["탑", "정글", "미드", "원딜", "서폿", "팀게임"], price: "100,000원 / 1시간", image: "assets/shineast.png", featuredImage: "assets/shineast2.png", detailImage: "assets/shineast2.png", imagePosition: "center center", featuredImagePosition: "center center", detailImagePosition: "center center", rating: 5.0, lessons: 212, reviews: [["사이니스트", "복기하면서 제가 맵을 거의 안 보고 있었다는 걸 깨달았어요."], ["미드연습중", "라인을 밀어야 할 때와 받아야 할 때가 구분됐어요."]], badges: ["최우수", "추천"], featuredAd: true },
  { id: "coach-shineast-mid-value", category: "league", name: "미드 가성비 리플레이", coachKey: "shineast", coachProfileName: "샤이니스트 코치", tier: "최우수", coachTier: "최우수", coachSummary: "프로팀 출신 · 모든 라인 피드백 · 팀게임 운영까지 가능", tagline: "미드 라인전, 로밍 타이밍, 한타 합류를 핵심 장면 중심으로 빠르게 교정", bio: "미드 리플레이를 중심으로 라인 주도권, 귀환 타이밍, 정글과의 턴 사용, 사이드 합류 판단을 압축해서 봅니다. 부담 없는 리플레이 점검형 상품입니다.", purpose: ["value", "mid"], roles: ["미드", "라인전", "로밍", "리플레이"], price: "50,000원 / 1게임", image: "assets/shineast.png", featuredImage: "assets/shineast2.png", detailImage: "assets/shineast2.png", imagePosition: "center center", featuredImagePosition: "center center", detailImagePosition: "center center", rating: 4.9, lessons: 84, reviews: [["미드연습중", "로밍을 가야 하는 타이밍이 명확해졌어요."], ["아지르유저", "라인을 밀고 뭘 해야 하는지 정리가 됐습니다."]], badges: ["추천", "리뷰 우수"] },
  { id: "coach-mireu", category: "league", name: "정미르 코치", coachKey: "mireu", coachProfileName: "정미르 코치", tier: "우수", coachTier: "우수", coachSummary: "우수 수강생 · 저티어 친화 · 정글/팀게임 피드백", tagline: "저티어와 일반 수강생에게 쉬운 정글 동선, 갱각, 오브젝트 판단 코칭", bio: "학교 강의 경험을 바탕으로 입문자와 저티어가 바로 적용할 수 있는 판단 기준을 쉽게 정리합니다. 정글 첫 동선, 갱각, 오브젝트 판단과 팀게임 피드백을 부담 없는 가격대로 진행합니다.", purpose: ["jungle", "low", "team", "value"], roles: ["정글", "저티어", "팀게임", "입문"], price: "35,000원 / 1시간", image: "assets/mireu.png", featuredImage: "assets/mireu2.png", detailImage: "assets/mireu2.png", imagePosition: "center center", featuredImagePosition: "center center", detailImagePosition: "center center", rating: 4.6, lessons: 72, reviews: [["게스트", "이전 리플레이로 설명해주셔서 이해가 빨랐어요."], ["입문자", "연습 순서가 생겨서 좋았습니다."]], badges: ["우수", "입문 추천"] },
  { id: "coach-mireu-jungle-basic", category: "league", name: "저티어 정글 동선 입문", coachKey: "mireu", coachProfileName: "정미르 코치", tier: "우수", coachTier: "우수", coachSummary: "우수 수강생 · 저티어 친화 · 정글/팀게임 피드백", tagline: "첫 동선, 갱각, 오브젝트 판단을 저티어 기준으로 쉽게 정리하는 입문 코칭", bio: "정글을 막 시작했거나 동선이 자주 꼬이는 수강생에게 맞춘 강의입니다. 첫 캠프 선택, 라인 상태 읽기, 갱킹 타이밍, 용과 전령 판단을 쉬운 기준으로 정리합니다.", purpose: ["jungle", "low", "value"], roles: ["정글", "저티어", "입문", "오브젝트"], price: "25,000원 / 1게임", image: "assets/mireu.png", featuredImage: "assets/mireu2.png", detailImage: "assets/mireu2.png", imagePosition: "center center", featuredImagePosition: "center center", detailImagePosition: "center center", rating: 4.6, lessons: 38, reviews: [["브론즈정글", "첫 동선 기준이 생겼어요."], ["누누연습", "오브젝트를 언제 쳐야 하는지 알겠어요."]], badges: ["입문 추천", "저티어 입문"] },
  { id: "coach-persona", category: "league", name: "페르소나 코치", coachKey: "persona", coachProfileName: "페르소나 코치", tier: "우수", coachTier: "우수", coachSummary: "탑 라이너 출신 · 이론 중심 · 고티어까지 가능", tagline: "탑 라인 매치업, 웨이브, 텔 타이밍을 이론 중심으로 정리하는 코칭", bio: "탑 라인에서 손해를 보는 구간을 매치업과 웨이브 기준으로 분석합니다. 라인전 이론, 텔레포트 타이밍, 사이드 운영처럼 탑 라이너에게 중요한 판단을 리플레이로 점검합니다.", purpose: ["top", "high", "value"], roles: ["탑", "라인전", "고티어", "이론"], price: "45,000원 / 1시간", image: "assets/persona2.png", featuredImage: "assets/persona.png", detailImage: "assets/persona.png", imagePosition: "center center", featuredImagePosition: "center center", detailImagePosition: "center center", rating: 4.5, lessons: 41, reviews: [["게스트", "지게 보는 각도 고칠 게 명확했습니다."], ["초보탑", "뭘 몰라서 지는지 알게 됐어요."]], badges: ["우수"] },
  { id: "coach-persona-top-matchup", category: "league", name: "탑 매치업 집중 리플레이", coachKey: "persona", coachProfileName: "페르소나 코치", tier: "우수", coachTier: "우수", coachSummary: "탑 라이너 출신 · 이론 중심 · 고티어까지 가능", tagline: "탑 라인 매치업과 웨이브 손해 구간을 한 게임 단위로 짚는 리플레이 코칭", bio: "탑 라인에서 솔킬각, 웨이브 위치, 귀환 타이밍, 텔레포트 사용을 매치업별로 점검합니다. 특정 챔피언 상대법을 빠르게 정리하고 싶은 수강생에게 맞춘 상품입니다.", purpose: ["top", "value"], roles: ["탑", "매치업", "라인전", "웨이브"], price: "30,000원 / 1게임", image: "assets/persona2.png", featuredImage: "assets/persona.png", detailImage: "assets/persona.png", imagePosition: "center center", featuredImagePosition: "center center", detailImagePosition: "center center", rating: 4.5, lessons: 29, reviews: [["탑연습", "상성 때문에 지는 줄 알았는데 웨이브가 문제였어요."], ["잭스유저", "딜교 타이밍이 훨씬 명확해졌습니다."]], badges: ["추천", "우수"] },
  { id: "coach-mephi", category: "league", name: "메피 코치", coachKey: "mephi", coachProfileName: "메피 코치", tier: "엠버서더", coachTier: "엠버서더", coachSummary: "전프로 바텀 라이너 · 전 라인 피드백 · 팀게임 리뷰 가능", tagline: "바텀 라인전과 전 라인 리플레이를 전프로 관점으로 보는 코칭", bio: "시즌 5부터 현재까지 챌린저를 유지한 바텀 라이너 관점으로 라인전, 교전, 한타 포지션을 점검합니다. 전 라인 피드백과 팀게임 리뷰까지 가능하며, 운영과 시야 컨트롤도 함께 봅니다.", purpose: ["adc", "support", "team", "high"], roles: ["원딜", "서폿", "전 라인", "팀게임"], price: "70,000원 / 1시간", image: "assets/mephi.png", featuredImage: "assets/mephi2.png", detailImage: "assets/mephi2.png", imagePosition: "center center", featuredImagePosition: "center center", detailImagePosition: "center center", rating: 4.8, lessons: 103, reviews: [["리조또", "라인전 전에 계속 뭘 봐야 하는지 처음으로 이해됐어요."], ["봄", "상대 정글 위치를 근거로 플레이하는 법을 배웠습니다."]], badges: ["엠버서더", "추천"], featuredAd: true },
  { id: "coach-mephi-bot-lane", category: "league", name: "바텀 라인전 듀오 피드백", coachKey: "mephi", coachProfileName: "메피 코치", tier: "엠버서더", coachTier: "엠버서더", coachSummary: "전프로 바텀 라이너 · 전 라인 피드백 · 팀게임 리뷰 가능", tagline: "원딜과 서폿의 라인전 합, 선2렙, 교전각을 전프로 관점으로 점검", bio: "바텀 듀오 또는 원딜/서폿 개인에게 맞춘 상품입니다. 선2렙 설계, 미니언 웨이브, 시야 타이밍, 용 전 교전 준비를 리플레이로 정리합니다.", purpose: ["adc", "support", "high", "value"], roles: ["원딜", "서폿", "라인전", "교전"], price: "55,000원 / 1게임", image: "assets/mephi.png", featuredImage: "assets/mephi2.png", detailImage: "assets/mephi2.png", imagePosition: "center center", featuredImagePosition: "center center", detailImagePosition: "center center", rating: 4.8, lessons: 67, reviews: [["원딜유저", "서폿이랑 언제 싸워야 하는지 알게 됐어요."], ["서폿연습", "와드 타이밍이 훨씬 깔끔해졌습니다."]], badges: ["엠버서더", "리뷰 우수"] },
];

export const initialBookings = [];

export const imageMigration = {
  "assets/logo.png": "assets/logo.jpg",
  "assets/lol-logo.png": "assets/logo.jpg",
  "assets/lollogo.png": "assets/logo.jpg",
  "assets/NSshineast.jpg": "assets/shineast.png",
  "assets/mephicoach.png": "assets/mephi.png",
  "assets/mireucoach.png": "assets/mireu.png",
  "assets/personacoach.png": "assets/persona2.png",
};
export const tierRank = { "엠버서더": 0, "최우수": 1, "우수": 2, "일반": 3 };

export const leagueLessonOverrides = {
  "coach-shineast": { coachKey: "shineast", purpose: ["value", "team", "high", "mid"] },
  "coach-mireu": { coachKey: "mireu" },
  "coach-persona": { coachKey: "persona" },
  "coach-mephi": { coachKey: "mephi" },
};
export const legacyCoachKeys = { "lol-1": "persona", "lol-2": "shineast", "lol-3": "mireu", "lol-5": "mephi" };
export const state = {
  activeView: "market",
  category: "league",
  type: "all",
  segment: "all",
  selectedCoachId: null,
  selectedCoachKey: null,
  recentCoachKeys: [],
  coachSelfKey: "shineast",
  coachSelfLessonId: null,
  query: "",
  coachExplorerQuery: "",
  coachExplorerRole: "all",
  coachExplorerTier: "all",
  coaches: [],
  coachSelfLessons: null,
  coachLoadState: "idle",
  adminCoachSettings: [],
  adminCoachSettingsLoadState: "idle",
  adminCoachSettingsLoadError: "",
  adminCoachSettingsRequestId: 0,
  adminCoachQuery: "",
  adminSelectedCoachKey: "",
  bookings: [],
  bookingLoadState: "idle",
  bookingLoadError: "",
  bookingRequestId: 0,
  coachDashboardLoadState: "idle",
  coachDashboardLoadError: "",
  studentReservationLoadState: "idle",
  studentReservationLoadError: "",
  bookingFilterStatus: "all",
  bookingQuery: "",
  bookingPendingStatuses: {},
  selectedBookingId: null,
  users: [],
  userLoadState: "idle",
  userLoadError: "",
  userRequestId: 0,
  userQuery: "",
  userSaveStates: {},
  coachRequests: [],
  coachRequestLoadState: "idle",
  coachRequestLoadError: "",
  cropSourceImage: "",
  cropTarget: null,
  coachProfile: null,
  coachProfileLoadState: "idle",
  coachProfileLoadError: "",
  currentUser: null,
  authLoadState: "idle",
  authRequestId: 0,
  accountOverview: null,
  accountOverviewLoadState: "idle",
  availabilityByCoach: {},
  availabilityLoadStates: {},
  coachAvailability: [],
  coachAvailabilityLoadState: "idle",
  coachAvailabilityLoadError: "",
  coachSchedule: { weekly: [], overrides: [], slots: [] },
  coachScheduleLoadState: "idle",
  coachScheduleLoadError: "",
  coachScheduleWeekStart: "",
  coachScheduleDraft: null,
  coachScheduleShowAllHours: false,
  coachScheduleEditMode: "weekly",
  refundRequests: [],
  adminRefundRequests: [],
  refundAdminLoadState: "idle",
  refundAdminLoadError: "",
  reviewsByCoach: {},
  submittedReviewIds: [],
};
