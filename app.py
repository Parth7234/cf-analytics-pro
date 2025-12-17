import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import google.generativeai as genai
from datetime import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="CF Analytics Pro", page_icon="⚔️", layout="wide")

st.title("⚔️ Codeforces Analytics: Pro Edition")
st.markdown("### The ultimate tool to benchmark your CP performance.")

# --- UTILITY FUNCTIONS ---
@st.cache_data(ttl=3600) 
def fetch_user_data(handle):
    base_url = "https://codeforces.com/api"
    try:
        # 1. User Info
        info = requests.get(f"{base_url}/user.info?handles={handle}").json()
        if info['status'] != 'OK': return None, None
        
        # 2. Submissions
        subs = requests.get(f"{base_url}/user.status?handle={handle}").json()
        if subs['status'] != 'OK': return None, None
        
        return info['result'][0], subs['result']
    except:
        return None, None

def process_submissions(submissions):
    data = []
    for sub in submissions:
        if 'problem' in sub and 'rating' in sub['problem']:
            # Timestamp conversion
            ts = int(sub['creationTimeSeconds'])
            date_solved = datetime.fromtimestamp(ts).date()
            
            data.append({
                'Problem': sub['problem']['name'],
                'Rating': sub['problem']['rating'],
                'Tags': sub['problem']['tags'],
                'Verdict': sub['verdict'],
                'Date': date_solved,
                # NEW FIELDS FOR LINKS (Required for Upsolve Feature)
                'ContestId': sub['problem'].get('contestId', 0),
                'Index': sub['problem'].get('index', '')
            })
    return pd.DataFrame(data)

def generate_ai_coach_response(handle, rating, max_rating, strong_tags, weak_tags):
    try:
        # 1. Check for API Key
        if "GEMINI_API_KEY" not in st.secrets:
            return "❌ Error: API Key missing! Please add GEMINI_API_KEY to .streamlit/secrets.toml"
            
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        
        # 2. Select Model (Updated to 2.5 Flash for speed/quality balance)
        model = genai.GenerativeModel('gemini-2.5-flash')

        # 3. Construct Prompt
        prompt = f"""
        You are a legendary Competitive Programming Coach (strict but encouraging). 
        Analyze this student's profile:
        
        - Handle: {handle}
        - Current Rating: {rating} (Max: {max_rating})
        - Strong Topics: {', '.join(strong_tags[:3])}
        - Weak Topics: {', '.join(weak_tags[:3])}

        Your Task:
        1. Give a 2-sentence summary of their profile.
        2. Suggest a specific 3-step roadmap to reach the next rating tier.
        3. Recommend one specific algorithm they should learn next based on their weak topics.
        
        Keep it concise, professional, and motivating. Use Markdown formatting.
        """

        # 4. Generate
        response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        return f"⚠️ AI Error: {str(e)}"

# --- SIDEBAR & MODES ---
st.sidebar.header("⚙️ Dashboard Controls")
mode = st.sidebar.radio("Select Mode", ["👤 Single Player Analysis", "⚔️ Head-to-Head Comparison"])

if mode == "👤 Single Player Analysis":
    handle = st.sidebar.text_input("Enter Codeforces Handle:", value="tourist")
    
    # Check if a new user is searched, clear previous AI result
    if 'last_handle' not in st.session_state or st.session_state.last_handle != handle:
        st.session_state.ai_result = None
        st.session_state.last_handle = handle
    
    if st.sidebar.button("Analyze Profile"):
        st.session_state.analyze_clicked = True

    # Main Analysis Logic
    if st.session_state.get('analyze_clicked'):
        with st.spinner("Fetching Codeforces Data..."):
            user_info, subs = fetch_user_data(handle)
            
            if not user_info:
                st.error(f"User '{handle}' not found or API issue.")
            else:
                df = process_submissions(subs)
                ac_df = df[df['Verdict'] == 'OK']

                # --- PRE-CALCULATE DATA (So it's available for AI) ---
                all_tags = [tag for tags in ac_df['Tags'] for tag in tags]
                if all_tags:
                    tag_counts = pd.Series(all_tags).value_counts().reset_index()
                    tag_counts.columns = ['Topic', 'Count']
                else:
                    tag_counts = pd.DataFrame(columns=['Topic', 'Count'])

                # --- TOP STATS ROW ---
                st.markdown("---")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Current Rating", user_info.get('rating', 'Unrated'))
                c2.metric("Max Rating", user_info.get('maxRating', 'Unrated'))
                c3.metric("Problems Solved (AC)", len(ac_df))
                
                if not ac_df.empty:
                    daily_counts = ac_df.groupby('Date').size()
                    max_day = daily_counts.max()
                    c4.metric("Best Day Record", f"{max_day} Problems")
                else:
                    c4.metric("Best Day", 0)

                # --- TABS (Updated to 4 Tabs) ---
                tab1, tab2, tab3, tab4 = st.tabs(["📊 Ratings", "📅 Consistency", "🧠 Topics", "🔨 Upsolve"])

                with tab1:
                    st.subheader("Problem Rating Distribution")
                    rating_counts = ac_df['Rating'].value_counts().reset_index()
                    rating_counts.columns = ['Rating', 'Count']
                    fig = px.bar(rating_counts, x='Rating', y='Count', color='Count', color_continuous_scale='Viridis')
                    st.plotly_chart(fig, use_container_width=True)

                with tab2:
                    st.subheader("Submission Activity Log")
                    daily_activity = df.groupby('Date').size().reset_index(name='Submissions')
                    fig_cal = px.scatter(daily_activity, x='Date', y='Submissions', size='Submissions', color='Submissions', title="Daily Grind Heatmap")
                    st.plotly_chart(fig_cal, use_container_width=True)

                with tab3:
                    st.subheader("Topic Strengths")
                    if not tag_counts.empty:
                        fig_radar = px.line_polar(tag_counts.head(10), r='Count', theta='Topic', line_close=True)
                        fig_radar.update_traces(fill='toself')
                        st.plotly_chart(fig_radar, use_container_width=True)
                    else:
                        st.info("No tags found.")

                with tab4:
                    st.subheader("Recommended Upsolving (Last 5)")
                    st.caption("Problems you attempted but haven't solved yet. Click to open.")

                    # Logic: Find problems attempted but NEVER solved
                    solved_problems = set(ac_df['Problem'])
                    # Filter for Attempted but NOT Solved
                    failed_df = df[~df['Problem'].isin(solved_problems)].copy()

                    if not failed_df.empty:
                        # Remove duplicates (keep the most recent attempt)
                        unique_failed = failed_df.drop_duplicates(subset=['Problem'], keep='first')
                        
                        # Sort by Date (Descending) to show recent failures first
                        recent_failures = unique_failed.sort_values(by='Date', ascending=False).head(5)
                        
                        # Display with Links
                        for i, row in recent_failures.iterrows():
                            # Construct URL: https://codeforces.com/contest/{id}/problem/{index}
                            url = f"https://codeforces.com/contest/{row['ContestId']}/problem/{row['Index']}"
                            
                            st.markdown(f"""
                            <div style="padding: 10px; border: 1px solid #e0e0e0; border-radius: 5px; margin-bottom: 10px; background-color: #ffffff;">
                                <b>{i+1}. <a href="{url}" target="_blank" style="text-decoration: none; color: #007bff;">{row['Problem']}</a></b> 
                                <span style="float: right; color: #666;">Rating: <b>{row['Rating']}</b></span>
                                <br>
                                <small style="color: #888;">Last attempted: {row['Date']}</small>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.success("🎉 Clean Sheet! You have solved every problem you attempted.")

                # --- AI COACH SECTION ---
                st.markdown("---")
                st.subheader("🤖 AI Coach Assessment")
                st.info("Get personalized advice powered by **Gemini 2.5 Flash**.")
                
                # Button to trigger AI
                if st.button("✨ Generate Roadmap"):
                    if not all_tags:
                        st.warning("Not enough data for AI analysis.")
                    else:
                        with st.spinner("Consulting the algorithm gods..."):
                            strongest = tag_counts.head(3)['Topic'].tolist()
                            weakest = tag_counts.tail(3)['Topic'].tolist()
                            
                            # Save result to session state so it persists
                            st.session_state.ai_result = generate_ai_coach_response(
                                handle, 
                                user_info.get('rating', 0), 
                                user_info.get('maxRating', 0), 
                                strongest, 
                                weakest
                            )

                # Display the result if it exists in session state
                if st.session_state.get('ai_result'):
                    st.success("Coach's Report Ready!")
                    st.markdown(f"""
                    <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #ff4b4b; color: #000000;">
                        {st.session_state.ai_result}
                    </div>
                    """, unsafe_allow_html=True)

elif mode == "⚔️ Head-to-Head Comparison":
    st.sidebar.markdown("---")
    h1 = st.sidebar.text_input("Player 1 Handle:", value="tourist")
    h2 = st.sidebar.text_input("Player 2 Handle:", value="Petr")
    
    if st.sidebar.button("Run Comparison"):
        with st.spinner("Crunching numbers..."):
            u1_info, u1_subs = fetch_user_data(h1)
            u2_info, u2_subs = fetch_user_data(h2)
            
            if u1_info and u2_info:
                df1 = process_submissions(u1_subs)
                df2 = process_submissions(u2_subs)
                
                ac1 = df1[df1['Verdict'] == 'OK']
                ac2 = df2[df2['Verdict'] == 'OK']

                st.markdown(f"## ⚔️ {h1} vs {h2}")
                
                c1, c2 = st.columns(2)
                r1 = u1_info.get('rating', 0)
                r2 = u2_info.get('rating', 0)
                c1.metric(f"{h1} Rating", r1, delta=r1-r2)
                c2.metric(f"{h2} Rating", r2, delta=r2-r1)

                p1_set = set(ac1['Problem'])
                p2_set = set(ac2['Problem'])
                common = len(p1_set.intersection(p2_set))
                
                st.success(f"🤝 **Similarity Score:** You have solved **{common}** of the same problems.")

                st.subheader("Who solves harder problems?")
                r1_counts = ac1['Rating'].value_counts().reset_index()
                r1_counts['User'] = h1
                r1_counts.columns = ['Rating', 'Count', 'User']
                
                r2_counts = ac2['Rating'].value_counts().reset_index()
                r2_counts['User'] = h2
                r2_counts.columns = ['Rating', 'Count', 'User']
                
                combined = pd.concat([r1_counts, r2_counts])
                
                fig_compare = px.bar(combined, x='Rating', y='Count', color='User', barmode='group')
                st.plotly_chart(fig_compare, use_container_width=True)
            else:
                st.error("One or both users invalid.")