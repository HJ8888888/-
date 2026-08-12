import streamlit as st
import time
import pandas as pd
import json

# ==========================================
# 0. Page Config & Custom CSS Styling
# ==========================================
st.set_page_config(
    page_title="라이브 퀴즈 챌린지",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Soft Cream & Warm Pastel Palette
st.markdown("""
<style>
    /* Global Background & Font */
    .main {
        background-color: #FAF5F6;
        color: #523E43;
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
    }
    
    /* Headers */
    h1, h2, h3, h4 {
        color: #523E43 !important;
        font-weight: 700;
    }
    
    /* Buttons */
    .stButton>button {
        background-color: #EED7DC !important;
        color: #523E43 !important;
        border-radius: 12px !important;
        border: 1px solid #E2C2C9 !important;
        padding: 0.5rem 1.2rem !important;
        font-weight: 600 !important;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        background-color: #E2C2C9 !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(82, 62, 67, 0.08);
    }
    
    /* Cards & Containers */
    .quiz-card {
        background-color: #FFFFFF;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 4px 20px rgba(226, 194, 201, 0.2);
        border: 1px solid #F3E5E8;
        margin-bottom: 20px;
    }
    
    .timer-badge {
        font-size: 28px;
        font-weight: 800;
        color: #D96B82;
        background-color: #FFF0F3;
        padding: 8px 20px;
        border-radius: 30px;
        display: inline-block;
        border: 2px solid #F8C8D4;
    }

    .stat-card-correct {
        background-color: #E8F5E9;
        border: 2px solid #A5D6A7;
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 10px;
        color: #1B5E20;
        font-weight: 600;
    }
    
    .stat-card-normal {
        background-color: #F8F9FA;
        border: 1px solid #E9ECEF;
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 10px;
        color: #495057;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #F7EBEF;
        border-right: 1px solid #EED7DC;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. Global Game State Management
# ==========================================
@st.cache_resource
def get_global_game():
    return {
        "status": "waiting",        # waiting, running, finished
        "curr_q": 0,
        "q_start_time": 0.0,
        "questions": [],
        "answers": {},              # {q_idx: {nickname: choice_list_or_str}}
        "participants": [],         # list of nicknames
        "timer_sec_obj": 15,        # 객관식 시간초
        "timer_sec_subj": 30        # 주관식 시간초
    }

game = get_global_game()

# Helper: Parse raw answer string into list of clean correct answers
def parse_correct_answers(ans_raw):
    if isinstance(ans_raw, list):
        return [str(a).strip() for a in ans_raw if str(a).strip()]
    ans_str = str(ans_raw).strip()
    parts = [p.strip() for p in ans_str.replace(";", ",").replace("/", ",").split(",") if p.strip()]
    clean_parts = []
    for p in parts:
        if p.isdigit() or (p.replace('.', '', 1).isdigit() and p.count('.') == 1):
            clean_parts.append(str(int(float(p))))
        else:
            clean_parts.append(p)
    return clean_parts

# Helper: Parse Excel/Text into standard questions list
def process_questions_df(df):
    q_list = []
    for idx, row in df.iterrows():
        q_text = str(row.get("문제", "")).strip()
        q_type = str(row.get("유형", "객관식")).strip()
        ans_raw = row.get("정답", "")
        parsed_ans = parse_correct_answers(ans_raw)
        
        options = []
        if "주관식" not in q_type:
            for opt_key in ["보기1", "보기2", "보기3", "보기4", "보기5"]:
                if opt_key in row and pd.notna(row[opt_key]):
                    val = str(row[opt_key]).strip()
                    if val:
                        options.append(val)
        
        # 개별 제한시간 설정 확인
        custom_timer = None
        for t_col in ["제한시간", "제한시간(초)", "시간"]:
            if t_col in row and pd.notna(row[t_col]):
                try:
                    custom_timer = int(row[t_col])
                except:
                    pass

        if q_text:
            q_dict = {
                "q": q_text,
                "type": "subjective" if "주관식" in q_type else "objective",
                "options": options,
                "ans": parsed_ans
            }
            if custom_timer and custom_timer > 0:
                q_dict["timer"] = custom_timer
            q_list.append(q_dict)
    return q_list

# Helper: Calculate user score
def calculate_scores():
    scores = {p: 0 for p in game["participants"]}
    for q_idx, q_data in enumerate(game["questions"]):
        q_answers = game["answers"].get(q_idx, {})
        correct_ans = q_data["ans"]
        
        for p, user_ans in q_answers.items():
            if p not in scores:
                scores[p] = 0
                
            if q_data["type"] == "objective":
                # Convert user selection to option indices list
                if isinstance(user_ans, list):
                    user_indices = [str(a).split(".")[0].strip() for a in user_ans]
                else:
                    user_indices = [str(user_ans).split(".")[0].strip()]
                
                # Check exact match for multi-choice
                if sorted(user_indices) == sorted(correct_ans):
                    scores[p] += 1
            else:
                # Subjective comparison
                u_str = str(user_ans).strip().lower()
                c_strs = [c.lower() for c in correct_ans]
                if u_str in c_strs:
                    scores[p] += 1
    return scores


# ==========================================
# 2. Sidebar Mode Switcher
# ==========================================
st.sidebar.title("💡 라이브 퀴즈 챌린지")
mode = st.sidebar.radio("모드 선택", ["진행자 모드 (Host)", "참가자 모드 (Participant)"])

st.sidebar.markdown("---")
st.sidebar.markdown(f"**현재 접속 인원:** {len(game['participants'])} / 100 명")
st.sidebar.markdown(f"**등록된 문제 수:** {len(game['questions'])} 개")


# ==========================================
# 3. 진행자 모드 (HOST MODE)
# ==========================================
if mode == "진행자 모드 (Host)":
    # 비밀번호 인증 상태 확인
    if "host_authenticated" not in st.session_state:
        st.session_state["host_authenticated"] = False

    if not st.session_state["host_authenticated"]:
        st.title("🔒 진행자 모드 비밀번호 인증")
        st.write("진행자 모드에 접근하려면 비밀번호를 입력해주세요.")
        
        with st.form(key="host_auth_form"):
            input_password = st.text_input("비밀번호 입력", type="password")
            auth_submit = st.form_submit_button("🔑 접속하기")
            
            if auth_submit:
                if input_password == "sunghejinH8!":
                    st.session_state["host_authenticated"] = True
                    st.success("인증에 성공했습니다!")
                    st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다. 다시 입력해 주세요.")
    else:
        # 인증 성공 시 진행자 메인 화면
        st.title("🎬 진행자 제어판 (Host Panel)")
        
        # 진행자 로그아웃 (잠금) 버튼
        if st.sidebar.button("🔒 진행자 모드 잠금 (로그아웃)"):
            st.session_state["host_authenticated"] = False
            st.rerun()

        tabs = st.tabs(["🎮 게임 진행", "⚙️ 문제 관리 & 설정", "📊 실시간 현황 & 순위"])
        
        # --------------------------------------
        # TAB 1: 게임 진행
        # --------------------------------------
        with tabs[0]:
            col_ctrl1, col_ctrl2 = st.columns([2, 1])
            
            with col_ctrl1:
                st.subheader("🎯 Quiz 진행 상태")
                if game["status"] == "waiting":
                    st.info("게임 시작 전입니다. 문제를 등록하고 [게임 시작] 버튼을 눌러주세요.")
                    if st.button("🚀 게임 시작하기", use_container_width=True):
                        if len(game["questions"]) == 0:
                            st.error("등록된 문제가 없습니다! '문제 관리 & 설정' 탭에서 문제를 추가해주세요.")
                        else:
                            game["status"] = "running"
                            game["curr_q"] = 0
                            game["q_start_time"] = time.time()
                            game["answers"] = {}
                            st.rerun()
                            
                elif game["status"] == "running":
                    curr_q = game["curr_q"]
                    total_q = len(game["questions"])
                    q_data = game["questions"][curr_q]
                    
                    # Dynamic timer check
                    q_type = q_data["type"]
                    limit = q_data.get("timer") or (game["timer_sec_subj"] if q_type == "subjective" else game["timer_sec_obj"])
                    elapsed = time.time() - game.get("q_start_time", time.time())
                    time_left = max(0, int(limit - elapsed))
                    
                    # Question Display
                    st.markdown(f"### Q{curr_q + 1}. {q_data['q']} ({'주관식' if q_type == 'subjective' else '객관식'})")
                    
                    # Options list (if objective)
                    if q_type == "objective":
                        for opt in q_data["options"]:
                            st.write(f"- {opt}")
                    
                    st.markdown("---")
                    
                    # Fragment for smooth live timer updates
                    @st.fragment(run_every="1s")
                    def host_timer_fragment():
                        e = time.time() - game.get("q_start_time", time.time())
                        t_left = max(0, int(limit - e))
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"<div class='timer-badge'>⏱️ 남은 시간: {t_left} 초</div>", unsafe_allow_html=True)
                        with c2:
                            ans_count = len(game["answers"].get(curr_q, {}))
                            part_count = len(game["participants"])
                            st.metric("답안 제출 현황", f"{ans_count} / {part_count} 명")
                        
                        st.markdown("---")
                        
                        if t_left > 0:
                            st.info("🔒 제한 시간이 지나면 정답과 선택 통계가 공개됩니다.")
                        else:
                            st.success(f"💡 **정답 공개:** {', '.join(q_data['ans'])}")
                            
                            st.subheader("📊 선택 통계 및 분석")
                            submits = game["answers"].get(curr_q, {})
                            total_submits = len(submits)
                            
                            if q_type == "objective":
                                # Count choices
                                opt_counts = {idx + 1: 0 for idx in range(len(q_data["options"]))}
                                for user_ans in submits.values():
                                    choices = user_ans if isinstance(user_ans, list) else [user_ans]
                                    for choice in choices:
                                        try:
                                            opt_num = int(str(choice).split(".")[0].strip())
                                            if opt_num in opt_counts:
                                                opt_counts[opt_num] += 1
                                        except:
                                            pass
                                
                                correct_indices = [int(a) for a in q_data["ans"] if a.isdigit()]
                                
                                for idx, opt in enumerate(q_data["options"], start=1):
                                    is_correct = idx in correct_indices
                                    cnt = opt_counts.get(idx, 0)
                                    pct = (cnt / total_submits * 100) if total_submits > 0 else 0
                                    
                                    if is_correct:
                                        st.markdown(f"""
                                        <div class='stat-card-correct'>
                                            ⭕ <b>{opt}</b> &nbsp;&nbsp;➔&nbsp;&nbsp; <b>{cnt}명 선택</b> ({pct:.1f}%) [정답]
                                        </div>
                                        """, unsafe_allow_html=True)
                                    else:
                                        st.markdown(f"""
                                        <div class='stat-card-normal'>
                                            ⚪ <b>{opt}</b> &nbsp;&nbsp;➔&nbsp;&nbsp; <b>{cnt}명 선택</b> ({pct:.1f}%)
                                        </div>
                                        """, unsafe_allow_html=True)
                            else:
                                # Subjective submitted responses summary
                                st.write(f"총 제출 인원: {total_submits}명")
                                if submits:
                                    resp_df = pd.DataFrame([{"참가자": k, "제출 답안": v} for k, v in submits.items()])
                                    st.dataframe(resp_df, use_container_width=True)

                    host_timer_fragment()
                    
                    # Navigation controls
                    st.markdown("---")
                    col_b1, col_b2, col_b3 = st.columns(3)
                    with col_b1:
                        if st.button("🔄 현재 문제 타이머 리셋"):
                            game["q_start_time"] = time.time()
                            st.rerun()
                    with col_b2:
                        if curr_q < total_q - 1:
                            if st.button("➡️ 다음 문제로 이동", use_container_width=True):
                                game["curr_q"] += 1
                                game["q_start_time"] = time.time()
                                st.rerun()
                        else:
                            if st.button("🏁 게임 종료 및 결과 보기", use_container_width=True):
                                game["status"] = "finished"
                                st.rerun()
                    with col_b3:
                        if st.button("🛑 게임 강제 리셋"):
                            game["status"] = "waiting"
                            game["curr_q"] = 0
                            game["answers"] = {}
                            st.rerun()
                            
                elif game["status"] == "finished":
                    st.balloons()
                    st.success("🎉 모든 문제가 종료되었습니다!")
                    
                    scores = calculate_scores()
                    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                    
                    st.subheader("🏆 최종 순위표")
                    rank_df = pd.DataFrame([{"순위": idx + 1, "닉네임": k, "점수": f"{v}점"} for idx, (k, v) in enumerate(sorted_scores)])
                    st.dataframe(rank_df, use_container_width=True)
                    
                    if st.button("🔄 새 게임 준비하기"):
                        game["status"] = "waiting"
                        game["curr_q"] = 0
                        game["answers"] = {}
                        st.rerun()

            with col_ctrl2:
                st.subheader("👥 실시간 참가자 목록")
                if game["participants"]:
                    for idx, p in enumerate(game["participants"], start=1):
                        st.write(f"{idx}. **{p}**")
                    st.markdown("---")
                    if st.button("🧹 참가자 목록 초기화", use_container_width=True):
                        game["participants"] = []
                        st.success("참가자 목록이 초기화되었습니다.")
                        st.rerun()
                else:
                    st.caption("아직 참가자가 없습니다.")

        # --------------------------------------
        # TAB 2: 문제 관리 & 설정
        # --------------------------------------
        with tabs[1]:
            st.subheader("⏱️ 유형별 제한시간 설정")
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                game["timer_sec_obj"] = st.number_input("객관식 제한시간 (초)", min_value=5, max_value=300, value=game["timer_sec_obj"])
            with col_t2:
                game["timer_sec_subj"] = st.number_input("주관식 제한시간 (초)", min_value=5, max_value=300, value=game["timer_sec_subj"])

            st.markdown("---")
            st.subheader("📥 문제 등록 (엑셀 업로드 / 직접 입력)")
            
            up_file = st.file_uploader("엑셀 파일 (.xlsx, .csv) 업로드", type=["xlsx", "csv"])
            if up_file is not None:
                try:
                    if up_file.name.endswith(".csv"):
                        df = pd.read_csv(up_file)
                    else:
                        df = pd.read_excel(up_file)
                    
                    st.write("📋 **업로드 파일 미리보기 (화면 공유 보호: 정답 가림)**")
                    preview_df = df.copy()
                    if "정답" in preview_df.columns:
                        preview_df["정답"] = "🔒 [비공개]"
                    st.dataframe(preview_df, use_container_width=True)
                    
                    if st.button("✅ 엑셀 문제 일괄 등록하기"):
                        q_list = process_questions_df(df)
                        game["questions"] = q_list
                        st.success(f"{len(q_list)}개의 문제가 성공적으로 등록되었습니다!")
                except Exception as e:
                    st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")

            st.markdown("---")
            st.subheader("📋 현재 등록된 문제 목록 및 편집")
            if game["questions"]:
                q_display = []
                for idx, q in enumerate(game["questions"], start=1):
                    def_time = game["timer_sec_subj"] if q["type"] == "subjective" else game["timer_sec_obj"]
                    q_time = q.get("timer", def_time)
                    ans_show = ", ".join(q["ans"]) if isinstance(q["ans"], list) else str(q["ans"])
                    q_display.append({
                        "번호": idx,
                        "문제": q["q"],
                        "유형": "주관식" if q["type"] == "subjective" else "객관식",
                        "제한시간(초)": q_time,
                        "보기 수": len(q["options"]),
                        "정답": ans_show
                    })
                st.dataframe(pd.DataFrame(q_display), use_container_width=True)
                
                st.markdown("---")
                st.subheader("✏️ 개별 문제 수정 및 삭제")
                
                q_indices = list(range(1, len(game["questions"]) + 1))
                selected_num = st.selectbox("수정 또는 삭제할 문제 번호 선택", q_indices)
                
                if selected_num:
                    target_idx = selected_num - 1
                    target_q = game["questions"][target_idx]
                    
                    with st.expander(f"⚙️ Q{selected_num}번 문제 상세 수정", expanded=True):
                        with st.form(key=f"edit_form_{target_idx}"):
                            edit_q_text = st.text_input("문제 내용", value=target_q["q"])
                            edit_type_str = st.radio(
                                "문제 유형",
                                ["객관식", "주관식"],
                                index=0 if target_q["type"] == "objective" else 1,
                                horizontal=True
                            )
                            
                            def_t = game["timer_sec_subj"] if target_q["type"] == "subjective" else game["timer_sec_obj"]
                            current_timer = target_q.get("timer", def_t)
                            edit_timer = st.number_input("개별 제한시간 (초)", min_value=5, max_value=300, value=int(current_timer))
                            
                            edit_options = []
                            if edit_type_str == "객관식":
                                st.write("**보기 설정 (객관식)**")
                                opts = target_q.get("options", [])
                                opt1 = st.text_input("보기 1", value=opts[0] if len(opts) > 0 else "")
                                opt2 = st.text_input("보기 2", value=opts[1] if len(opts) > 1 else "")
                                opt3 = st.text_input("보기 3", value=opts[2] if len(opts) > 2 else "")
                                opt4 = st.text_input("보기 4", value=opts[3] if len(opts) > 3 else "")
                                opt5 = st.text_input("보기 5 (선택)", value=opts[4] if len(opts) > 4 else "")
                                
                                for o in [opt1, opt2, opt3, opt4, opt5]:
                                    if o.strip():
                                        edit_options.append(o.strip())
                            
                            ans_str = ", ".join(target_q["ans"]) if isinstance(target_q["ans"], list) else str(target_q["ans"])
                            edit_ans_raw = st.text_input("정답 (객관식은 보기 번호 예: 1 또는 1,2 / 주관식은 단어)", value=ans_str)
                            
                            save_btn = st.form_submit_button("💾 수정사항 저장", use_container_width=True)
                            
                            if save_btn:
                                parsed_ans = parse_correct_answers(edit_ans_raw)
                                game["questions"][target_idx] = {
                                    "q": edit_q_text.strip(),
                                    "type": "subjective" if edit_type_str == "주관식" else "objective",
                                    "options": edit_options if edit_type_str == "객관식" else [],
                                    "ans": parsed_ans,
                                    "timer": int(edit_timer)
                                }
                                st.success(f"Q{selected_num}번 문제가 수정되었습니다!")
                                st.rerun()

                        if st.button(f"🗑️ Q{selected_num}번 문제 개별 삭제", use_container_width=True):
                            game["questions"].pop(target_idx)
                            st.success(f"Q{selected_num}번 문제가 삭제되었습니다.")
                            st.rerun()

                st.markdown("---")
                if st.button("🗑️ 전체 문제 일괄 삭제"):
                    game["questions"] = []
                    st.rerun()
            else:
                st.info("등록된 문제가 없습니다.")

        # --------------------------------------
        # TAB 3: 실시간 현황 & 순위
        # --------------------------------------
        with tabs[2]:
            st.subheader("📊 참가자별 점수 현황")
            scores = calculate_scores()
            if scores:
                score_df = pd.DataFrame([{"닉네임": k, "점수": v} for k, v in scores.items()]).sort_values(by="점수", ascending=False)
                st.dataframe(score_df, use_container_width=True)
            else:
                st.info("참가자가 없거나 아직 제출된 답안이 없습니다.")


# ==========================================
# 4. 참가자 모드 (PARTICIPANT MODE)
# ==========================================
else:
    st.title("🙋 참가자 모드 (Participant)")
    
    # Participant Nickname Entry
    if "my_nickname" not in st.session_state:
        st.session_state["my_nickname"] = ""
        
    if not st.session_state["my_nickname"]:
        st.subheader("닉네임을 입력하고 입장해주세요")
        st.info("💡 **학과명_성명** 형식으로 입장해 주세요. (예: 경영학과_홍길동)")
        nickname_input = st.text_input("닉네임 입력 (학과명_성명)", max_chars=20)
        
        if st.button("입장하기"):
            nickname_clean = nickname_input.strip()
            if not nickname_clean:
                st.warning("닉네임을 입력해주세요!")
            elif nickname_clean in game["participants"]:
                st.error("이미 사용 중인 닉네임입니다. 다른 닉네임을 입력해주세요.")
            elif len(game["participants"]) >= 100:
                st.error("⛔ 현재 접속 인원이 가득 차 입장할 수 없습니다. (최대 100명 제한)")
            else:
                game["participants"].append(nickname_clean)
                st.session_state["my_nickname"] = nickname_clean
                st.rerun()
    else:
        nickname = st.session_state["my_nickname"]
        st.write(f"👋 반갑습니다, **{nickname}** 님!")
        
        if st.button("🚪 퇴장하기"):
            if nickname in game["participants"]:
                game["participants"].remove(nickname)
            st.session_state["my_nickname"] = ""
            st.rerun()
            
        st.markdown("---")
        
        # Participant Game View
        if game["status"] == "waiting":
            st.info("⏳ 진행자가 게임을 시작하기를 기다리고 있습니다...")
            
            @st.fragment(run_every="2s")
            def wait_fragment():
                if game["status"] == "running":
                    st.rerun()
            wait_fragment()
            
        elif game["status"] == "running":
            curr_q = game["curr_q"]
            st.session_state["rendered_q"] = curr_q
            st.session_state["rendered_status"] = game["status"]

            if curr_q >= len(game["questions"]):
                st.write("모든 문제가 끝났습니다. 진행자의 안내를 기다려주세요.")
                @st.fragment(run_every="1s")
                def end_wait_fragment():
                    if game["status"] != "running" or game["curr_q"] != curr_q:
                        st.rerun()
                end_wait_fragment()
            else:
                q_data = game["questions"][curr_q]
                q_type = q_data["type"]
                limit = q_data.get("timer") or (game["timer_sec_subj"] if q_type == "subjective" else game["timer_sec_obj"])
                
                # Dynamic timer calculation
                elapsed = time.time() - game.get("q_start_time", time.time())
                time_left = max(0, int(limit - elapsed))
                
                st.markdown(f"### Q{curr_q + 1}. {q_data['q']}")
                
                # Check previous submission for this question
                q_answers = game["answers"].setdefault(curr_q, {})
                prev_sub = q_answers.get(nickname, None)
                
                # Timer & Auto-Sync Fragment
                @st.fragment(run_every="1s")
                def participant_timer_fragment():
                    # Check if host moved to next question or changed game status
                    if st.session_state.get("rendered_q") != game["curr_q"] or st.session_state.get("rendered_status") != game["status"]:
                        st.rerun()

                    e = time.time() - game.get("q_start_time", time.time())
                    t_left = max(0, int(limit - e))
                    st.markdown(f"<div class='timer-badge'>⏱️ 남은 시간: {t_left} 초</div>", unsafe_allow_html=True)
                    return t_left
                
                t_left = participant_timer_fragment()
                
                # Display persistent status message
                if prev_sub is not None:
                    disp_ans = ", ".join(prev_sub) if isinstance(prev_sub, list) else str(prev_sub)
                    st.success(f"✅ 제출된 답안: **{disp_ans}** (제출 완료 / 수정 가능)")
                
                # Answer submission form (Allow edit if time_left > 0)
                if t_left > 0:
                    with st.form(key=f"answer_form_{curr_q}"):
                        if q_type == "objective":
                            default_vals = []
                            if isinstance(prev_sub, list):
                                default_vals = [opt for opt in q_data["options"] if opt in prev_sub or opt.split(".")[0].strip() in [s.split(".")[0].strip() for s in prev_sub]]
                            
                            user_ans = st.multiselect(
                                "정답을 선택하세요 (다중 선택 가능):",
                                options=q_data["options"],
                                default=default_vals
                            )
                        else:
                            # Subjective text input
                            default_str = str(prev_sub) if prev_sub is not None else ""
                            user_ans = st.text_input("정답 입력:", value=default_str)
                            
                        submit_btn = st.form_submit_button("📝 답안 제출 / 수정하기")
                        
                        if submit_btn:
                            if not user_ans:
                                st.warning("답안을 선택하거나 입력해주세요!")
                            else:
                                game["answers"][curr_q][nickname] = user_ans
                                st.success("답안이 성공적으로 저장되었습니다!")
                                st.rerun()
                else:
                    st.warning("⏰ 제한시간이 종료되었습니다.")
                    
                    if q_type == "objective":
                        st.subheader("📊 선택 결과 및 정답")
                        submits = game["answers"].get(curr_q, {})
                        total_submits = len(submits)
                        
                        opt_counts = {idx + 1: 0 for idx in range(len(q_data["options"]))}
                        for u_ans in submits.values():
                            choices = u_ans if isinstance(u_ans, list) else [u_ans]
                            for choice in choices:
                                try:
                                    opt_num = int(str(choice).split(".")[0].strip())
                                    if opt_num in opt_counts:
                                        opt_counts[opt_num] += 1
                                except:
                                    pass
                        
                        correct_indices = [int(a) for a in q_data["ans"] if a.isdigit()]
                        
                        for idx, opt in enumerate(q_data["options"], start=1):
                            is_correct = idx in correct_indices
                            cnt = opt_counts.get(idx, 0)
                            pct = (cnt / total_submits * 100) if total_submits > 0 else 0
                            
                            if is_correct:
                                st.markdown(f"<div class='stat-card-correct'>⭕ <b>{opt}</b> — {cnt}명 ({pct:.1f}%) [정답]</div>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"<div class='stat-card-normal'>⚪ <b>{opt}</b> — {cnt}명 ({pct:.1f}%)</div>", unsafe_allow_html=True)

        elif game["status"] == "finished":
            st.balloons()
            st.success("🎉 모든 퀴즈가 완료되었습니다!")
            scores = calculate_scores()
            my_score = scores.get(nickname, 0)
            st.markdown(f"### 🏆 {nickname} 님의 최종 점수: **{my_score}점**")
