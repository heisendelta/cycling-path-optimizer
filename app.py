import streamlit as st
import folium
from streamlit_folium import st_folium
# from streamlit_js_eval import streamlit_js_eval

from utils.routing import generate_map, get_image_ids, evenly_sample, get_image_to_url
import math

if 'map_obj' not in st.session_state:
    st.session_state.map_obj = None
if 'last_search' not in st.session_state:
    st.session_state.last_search = None
if 'path_shortest_details' not in st.session_state:
    st.session_state.path_shortest_details = None
if 'path_practical_details' not in st.session_state:
    st.session_state.path_practical_details = None
if 'street_view_image' not in st.session_state:
    st.session_state.street_view_image = None
if 'path_practical' not in st.session_state:
    st.session_state.path_practical = None

if 'current_image_index' not in st.session_state:
    st.session_state.current_image_index = 0
if 'sampled_images' not in st.session_state:
    st.session_state.sampled_images = []



st.markdown("""
    <style>
    html, body, [data-baseweb="container"], .block-container {
        margin: 0;
        padding: 0;
        overflow: hidden;
    }
    .main .block-container {
        padding-top: 0rem;
        padding-bottom: 0rem;
        padding-left: 0rem;
        padding-right: 0rem;
    }
    .stFolium {
    }
    div[data-testid="stVerticalBlock"] {
    }
    div[data-testid="column"] {
    }
    .st-key-left_col {
        padding: 1rem !important;
        width: 100%;
        background-color: #000 !important;
    }
            
    .slideshow-container {
        position: relative;
        width: 100%;
    }
    .slideshow-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }
    .slideshow-counter {
        text-align: center;
        font-weight: bold;
        color: #666;
    }
    </style>
    """, unsafe_allow_html=True)


st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

left_col, right_col = st.columns([4, 6], gap=None)
# screen_height = streamlit_js_eval(js_expressions="screen.height", key="SCR")

with left_col.container(key="left_col"):
    source = st.text_input("Source", "", label_visibility="collapsed", key="source_input")
    destination = st.text_input("Destination", "", label_visibility="collapsed", key="dest_input")
    
    if st.button("Search", use_container_width=True):
        with st.spinner("Generating optimal route..."):
            # if type(source) == str: source = int(source)
            # if type(destination) == str: destination = int(destination)

            st.session_state.map_obj, _, st.session_state.path_practical, st.session_state.path_shortest_details, st.session_state.path_practical_details = generate_map(source, destination)
            st.session_state.last_search = (source, destination)
            st.session_state.current_image_index = 0
            st.rerun()

    shortest_col, practical_col = st.columns(2, gap='small')
    with shortest_col:
        if st.session_state.map_obj and st.session_state.path_shortest_details:

            distance_shortest = st.session_state.path_shortest_details['length_m'] / 1000
            time_shortest = distance_shortest / 15 * 60  # assuming average speed of 15 km/h

            st.metric('Shortest Route', f"{st.session_state.path_shortest_details['safety'].capitalize()}")
            st.metric("Distance", f'{round(distance_shortest, 1)} km')
            # st.metric("Estimated Time", f'{math.floor(time_shortest)} min')
            # st.metric("Bike Lane Coverage", "78%")

    with practical_col:
        if st.session_state.map_obj and st.session_state.path_practical_details:

            distance_practical = st.session_state.path_practical_details['length_m'] / 1000
            distance_percent = (distance_practical - distance_shortest) / distance_shortest * 100
            time_practical = distance_practical / 15 * 60  # assuming average speed of 15 km/h

            st.metric('Optimal Route', f"{st.session_state.path_practical_details['safety'].capitalize()}")
            st.metric("Distance", f'{round(distance_practical, 1)} km', delta=f"+{round(distance_percent, 1)}%")
            # st.metric("Estimated Time", f"{math.floor(time_practical)} min")
            # st.metric("Bike Lane Coverage", "78%")

    shortest_col, practical_col = st.columns(2, gap='small')
    st.text(' ')
    with shortest_col:
        if st.session_state.map_obj and st.session_state.path_shortest_details:
            st.metric("Estimated Time", f'{math.floor(time_shortest)} min')
    
    with practical_col:
        if st.session_state.map_obj and st.session_state.path_practical_details:
            st.metric("Estimated Time", f"{math.floor(time_practical)} min")

    if st.session_state.last_search:
        path_practical_images = get_image_ids(st.session_state.path_practical)
        sampled_images = evenly_sample(path_practical_images, 10)
        st.session_state.sampled_images = sampled_images

        # st.session_state.street_view_image = get_image_to_url(sampled_images[0])

        # # st.image(st.session_state.street_view_image, use_container_width=True, caption="Street View")
        # st.markdown('<div style="padding: 0; width: 100%;">', unsafe_allow_html=True)
        # st.image(st.session_state.street_view_image, use_container_width=True, caption="Street View")
        # st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="slideshow-container">', unsafe_allow_html=True)
    
        nav_col1, nav_col2, nav_col3 = st.columns([2, 6, 2])
        
        with nav_col1:
            if st.button("◀ Previous", use_container_width=True, key="prev_btn"):
                st.session_state.current_image_index -= 1
                st.session_state.current_image_index = st.session_state.current_image_index % len(st.session_state.sampled_images)
                st.rerun()
        
        with nav_col2:
            st.markdown(f'<div class="slideshow-counter">Image {st.session_state.current_image_index + 1} of {len(st.session_state.sampled_images)}</div>', 
                    unsafe_allow_html=True)
        
        with nav_col3:
            if st.button("Next ▶", use_container_width=True, key="next_btn"):
                st.session_state.current_image_index += 1
                st.session_state.current_image_index = st.session_state.current_image_index % len(st.session_state.sampled_images)
                st.rerun()
        
        current_image_url = get_image_to_url(st.session_state.sampled_images[st.session_state.current_image_index])
        st.image(current_image_url, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # st.image("https://scontent-nrt1-2.xx.fbcdn.net/m1/v/t6/An94J9sll0PHjSMr-o7lPbS-5o1wDuR57KsTGnUvS8LRD-FNKpqIOW0yCMztKQv6zzFISq6iaoYgALa_rblFpV-1j3xagnun_a0-0h-7YE-tOTFRT6MIkAboHmNMMuxfzb3m6KQbIVlpis37I-PTlA?stp=s2048x1536&_nc_gid=P58bTmjkKVJntnkiIIzyJQ&_nc_oc=Adlf-IW57DUCAbTvCFQ-leR9Ji7_Wcv1cJoWWhagEqcnE5TUEdaIaHQJldPlpTceTqc1RhXsUqjorJnwg0HRsteW&ccb=10-5&oh=00_AfW6EUZ_RgfObmcCwGPcfDTut4PetR1tHewf1BhvqrZlsw&oe=68D1E9A0&_nc_sid=201bca", use_container_width=True)


    # st.markdown('<div style="margin-top: auto !important; padding-top: 1rem !important;">', unsafe_allow_html=True)
    # st.image("https://scontent-nrt1-2.xx.fbcdn.net/m1/v/t6/An9xYzZxszTgXiKc8BFc4GRDZ43XpM5MirfkKCpbapy081eSkKdQzwjuVNEtDCDodwAOW9-a-m8m2Sjdcx2wvzqEJ0xwHEZUbT2C6S1n26A8XjZpuvNXis34PZ_GYvrh-k-7BeW3i4zTGIiXnd8Jw?stp=s2048x1152&_nc_gid=7yu3m_3bMOEth3v_lEUo0w&_nc_oc=AdlDTLbxXobL8nhdCXpzNRycv7eYoo6GjZg_cfeEJWUN5_Ci1-nTgldZgAclhW2vUWU4LtQRFdB6mHDcDnyLrsmb&ccb=10-5&oh=00_AfVaYD51OuflmxfbDx25-awXDyOrf3T72I7A0YHF3NXA9w&oe=68D12B1D&_nc_sid=201bca", use_container_width=True)
    # st.markdown('</div>', unsafe_allow_html=True)

# with right_col.container(key="right_col"):
#     m = folium.Map(
#         location=[35.68, 139.76],
#         zoom_start=12,
#         width="100%",
#         height=600
#     )
    
#     st_folium(
#         m, 
#         width=None,  # Let it use container width
#         height=940, # screen_height=1050
#         returned_objects=[],
#         key="static_map", # prevent refreshing
#         use_container_width=True,
#     )

with right_col:
    if st.session_state.map_obj:
        map_data = st_folium(
            st.session_state.map_obj,
            width=None,
            height=940,
            returned_objects=["last_clicked"],
            key="generated_map",
            use_container_width=True,
        )
    else:
        # Display empty map on first load
        # empty_map = folium.Map(
        #     location=[35.6895, 139.6917], 
        #     zoom_start=10,
        #     tiles='https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png',
        #     attr='<a href="https://github.com/cyclosm/cyclosm-cartocss-style/releases" title="CyclOSM - OpenBikeMap">CyclOSM</a> | Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        # )
        empty_map = folium.Map(
            location=[35.6895, 139.6917], 
            zoom_start=10
        )
        folium.TileLayer(
            tiles='https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png',
            attr='<a href="https://github.com/cyclosm/cyclosm-cartocss-style/releases" title="CyclOSM - OpenBikeMap">CyclOSM</a> | Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            name='CyclOSM',
            opacity=0.7,
            overlay=False
        ).add_to(empty_map)
        folium.TileLayer(
            tiles='CartoDB positron',
            name='CartoDB positron',
            opacity=0.2,
            overlay=False
        ).add_to(empty_map)
        folium.LayerControl().add_to(empty_map)
        st_folium(
            empty_map,
            width=None,
            height=600,
            returned_objects=[],
            key="empty_map"
        )
        st.info("Enter source and destination, then click Search to generate route")

if st.session_state.map_obj and 'last_clicked' in st.session_state:
    clicked_point = st.session_state.last_clicked
    st.write(f"Clicked at: {clicked_point['lat']:.4f}, {clicked_point['lng']:.4f}")
