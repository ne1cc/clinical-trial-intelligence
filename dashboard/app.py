"""Router — Clinical Trial Access & Recruitment Competition Intelligence."""

import streamlit as st

st.set_page_config(
    page_title="Clinical Trial Intelligence",
    page_icon=":material/monitor_heart:",
    layout="wide",
)

# Section order follows how a feasibility review is actually sequenced, which is
# why it does not match filename order: sponsor concentration is read before
# facility overlap.
NAVIGATION = {
    "": [
        st.Page(
            "pages/0_Overview.py",
            title="Overview",
            icon=":material/dashboard:",
            default=True,
        ),
    ],
    "Feasibility Signals": [
        st.Page(
            "pages/1_Priority_Queue.py",
            title="Priority Queue",
            icon=":material/format_list_numbered:",
        ),
        st.Page(
            "pages/2_Competition_Landscape.py",
            title="Competition Landscape",
            icon=":material/scatter_plot:",
        ),
        st.Page(
            "pages/3_Geography_Trends.py",
            title="Geography Trends",
            icon=":material/public:",
        ),
        st.Page(
            "pages/5_Sponsor_Landscape.py",
            title="Sponsor Landscape",
            icon=":material/apartment:",
        ),
        st.Page(
            "pages/4_Site_Overlap.py",
            title="Site Overlap",
            icon=":material/join_inner:",
        ),
    ],
    "Clinical Data Explorer": [
        st.Page(
            "pages/7_Trial_Explorer.py",
            title="Trial Explorer",
            icon=":material/search:",
        ),
        st.Page(
            "pages/8_Eligibility_Criteria.py",
            title="Eligibility Criteria",
            icon=":material/rule:",
        ),
        st.Page(
            "pages/9_OMOP_Explorer.py",
            title="OMOP Explorer",
            icon=":material/database:",
        ),
    ],
    "Forecasting & Data Trust": [
        st.Page(
            "pages/10_Enrollment_Forecast.py",
            title="Enrollment Forecast",
            icon=":material/trending_up:",
        ),
        st.Page(
            "pages/6_Data_Reliability.py",
            title="Data Reliability",
            icon=":material/verified:",
        ),
    ],
}

st.navigation(NAVIGATION).run()
