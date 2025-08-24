import pandas as pd
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
import folium
import json
from shapely.ops import linemerge
from shapely.geometry import LineString, box, MultiLineString
from scipy.spatial import cKDTree
from geopy.distance import great_circle
from collections import deque
import osmnx as ox
import math

# image_id to osmid
images_matches = gpd.read_parquet('utils/datasets/image_matches_n_3_yolo.parquet')
images_matches = images_matches[images_matches['pedestrians'] + images_matches['vehicles'] > 0]
images_matches.set_index('image_id', inplace=True)
images_matches = images_matches.to_crs("EPSG:4326")

# features
features = pd.read_parquet('utils/datasets/optimal_features.parquet')

# image to url
image_to_url = pd.read_parquet('utils/datasets/image_to_url.parquet')

# nodes and edges (roads)
north, east = 35.703152, 139.772041
south, west = 35.691657, 139.758834

G = ox.graph_from_bbox((east, south, west, north), network_type='bike', simplify=False)
nodes_gdf, roads_gdf = ox.graph_to_gdfs(G, nodes=True, edges=True)

# helper functions
def find_max_avg_path_pruned(G, optimal_df, start_node, end_node, max_depth=50):
    edge_optimals = {}
    for u, v, data in G.edges(data=True):
        osmids = data.get('osmid', [])
        if not isinstance(osmids, list):
            osmids = [osmids]
        edge_optimal = np.mean([optimal_df.loc[osmid, 'optimal'] for osmid in osmids
                              if osmid in optimal_df.index])
        edge_optimals[(u, v)] = edge_optimal

    best_at_node = {node: (-np.inf, 0, None) for node in G.nodes()}
    best_at_node[start_node] = (0, 0, [start_node])

    queue = deque([start_node])

    while queue:
        current = queue.popleft()
        current_avg, current_count, current_path = best_at_node[current]

        for neighbor in G.neighbors(current):
            if neighbor in current_path:
                continue

            edge_opt = edge_optimals.get((current, neighbor), 0)
            new_count = current_count + 1
            new_total = current_avg * current_count + edge_opt
            new_avg = new_total / new_count

            if new_avg > best_at_node[neighbor][0]:
                new_path = current_path + [neighbor]
                best_at_node[neighbor] = (new_avg, new_count, new_path)
                queue.append(neighbor)

    return best_at_node[end_node][2], best_at_node[end_node][0]

def get_path_optimality(path):
    optimality = 0

    for source_osmid, dest_osmid in nx.utils.pairwise(path):
        if (source_osmid, dest_osmid, 0) in roads_gdf.index:
            osmid = roads_gdf.loc[(source_osmid, dest_osmid, 0), 'osmid']
        elif (dest_osmid, source_osmid, 0) in roads_gdf.index:
            osmid = roads_gdf.loc[(dest_osmid, source_osmid, 0), 'osmid']
        else:
            print(f'Edge between {source_osmid} and {dest_osmid} not found')
            continue

        optimality += features.loc[osmid, 'optimal'].item()

    return optimality / len(path)

def geographic_length(geom):
    def calculate_linestring_length(line):
        coords = list(line.coords)
        total_distance = 0
        for i in range(len(coords) - 1):
            total_distance += great_circle(coords[i][::-1], coords[i + 1][::-1]).meters
        return total_distance

    if isinstance(geom, MultiLineString):
        total_length = 0
        print(geom)
        for line in geom.geoms:
            total_length += calculate_linestring_length(line)
        return total_length

    elif isinstance(geom, LineString):
        return calculate_linestring_length(geom)

    else:
        raise TypeError(f"Unsupported geometry type: {type(geom)}. Expected LineString or MultiLineString.")

def get_path_length(path):
    length = 0

    for source_osmid, dest_osmid in nx.utils.pairwise(path):
        if (source_osmid, dest_osmid, 0) in roads_gdf.index:
            geom = roads_gdf.loc[(source_osmid, dest_osmid, 0), 'geometry']
        elif (dest_osmid, source_osmid, 0) in roads_gdf.index:
            geom = roads_gdf.loc[(dest_osmid, source_osmid, 0), 'geometry']
        else:
            print(f'Edge between {source_osmid} and {dest_osmid} not found')
            continue

        length += geographic_length(geom)

    return length

def optimal_path_in_corridor(G, optimal_df, start_node, end_node, shortest_path, corridor_padding_percent=0.05, max_depth=50):
    
    path_nodes = [G.nodes[n] for n in shortest_path]
    lats = [node['y'] for node in path_nodes]
    lons = [node['x'] for node in path_nodes]
    
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    
    lat_width = max_lat - min_lat
    lon_width = max_lon - min_lon

    min_lat -= lat_width * corridor_padding_percent
    max_lat += lat_width * corridor_padding_percent
    min_lon -= lon_width * corridor_padding_percent
    max_lon += lon_width * corridor_padding_percent
    
    nodes_in_bbox = [
        n for n, data in G.nodes(data=True)
        if (min_lon <= data['x'] <= max_lon) and 
           (min_lat <= data['y'] <= max_lat)
    ]
    G_sub = G.subgraph(nodes_in_bbox).copy()
    
    optimal_path, optimality_score = find_max_avg_path_pruned(
        G_sub, optimal_df, start_node, end_node, max_depth
    )
    
    return optimal_path, optimality_score, (min_lon, min_lat, max_lon, max_lat)

def get_shortest_and_optimal_paths(G, optimal_df, source_point, dest_point):
    path_shortest = nx.shortest_path(G, source_point, dest_point)
    path_practical, optimality_practical, bbox_practical = optimal_path_in_corridor(
        G, optimal_df, source_point, dest_point, path_shortest, corridor_padding_percent=0.20
    )
    return path_shortest, path_practical, bbox_practical

def get_path_details(path):
    length = get_path_length(path)
    optimality = get_path_optimality(path)

    safety_array = ['empty', 'safe', 'caution', 'many caution'][::-1]
    safety = safety_array[math.floor(len(safety_array) * optimality)]

    return {
        'length_m': length,
        'optimality': optimality,
        'safety': safety,
    }

def get_nearest_node(G, query):
    try:
        lat, lon = ox.geocode(query)
        return ox.distance.nearest_nodes(G, lon, lat)
    except Exception as e:
        print(f"Geocoding failed: {e}")
        return None

def generate_map(source_query, dest_query):
    source_point = get_nearest_node(G, source_query)
    dest_point = get_nearest_node(G, dest_query)
    print(f"Source node: {source_point}, Destination node: {dest_point}")

    optimal_df = features[['optimal']]
    path_shortest, path_practical, bbox_practical = get_shortest_and_optimal_paths(
        G, optimal_df, source_point, dest_point
    )
    path_shortest_details = get_path_details(path_shortest)
    path_practical_details = get_path_details(path_practical)

    m = folium.Map(
        location=[sum((north, south)) / 2, sum((east, west)) / 2],
        zoom_start=16,
        # tiles='https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png',
        # attr='<a href="https://github.com/cyclosm/cyclosm-cartocss-style/releases" title="CyclOSM - OpenBikeMap">CyclOSM</a> | Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    )
    folium.TileLayer(
        tiles='https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png',
        attr='<a href="https://github.com/cyclosm/cyclosm-cartocss-style/releases" title="CyclOSM - OpenBikeMap">CyclOSM</a> | Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        name='CyclOSM',
        opacity=0.7,
        overlay=False
    ).add_to(m)
    folium.TileLayer(
        tiles='CartoDB positron',
        name='CartoDB positron',
        opacity=0.2,
        overlay=False
    ).add_to(m)
    folium.LayerControl().add_to(m)

    # rectangle_bounds = [[min(north, south), min(east, west)], [max(north, south), max(east, west)]]

    # folium.Rectangle(
    #     bounds=rectangle_bounds,
    #     color=None,
    #     fill=True,
    #     fill_color='#eb4d4b',
    #     fill_opacity=0.2,
    # ).add_to(m)

    # folium.Rectangle(
    #     bounds=[[bbox_practical[1], bbox_practical[0]], [bbox_practical[3], bbox_practical[2]]],
    #     color=None,
    #     fill=True,
    #     fill_color='#f39c12',
    #     fill_opacity=0.2,
    # ).add_to(m)

    points_list = [(nodes_gdf.loc[source_point, 'y'], nodes_gdf.loc[source_point, 'x']),
                 (nodes_gdf.loc[dest_point, 'y'], nodes_gdf.loc[dest_point, 'x'])]
    for coords in points_list:
        folium.CircleMarker(
            location=coords,
            radius=2,
            color="#4834d4",
        ).add_to(m)

    def draw_path(m, path_to_plot, color='cornflowerblue'):
        for source_osmid, dest_osmid in nx.utils.pairwise(path_to_plot):
            if (source_osmid, dest_osmid, 0) in roads_gdf.index:
                row = roads_gdf.loc[(source_osmid, dest_osmid, 0)]
            elif (dest_osmid, source_osmid, 0) in roads_gdf.index:
                row = roads_gdf.loc[(dest_osmid, source_osmid, 0)]
            else:
                print(f'Edge between {source_osmid} and {dest_osmid} not found')
                continue

            folium.PolyLine(
                locations=[(lat, lon) for lon, lat in row['geometry'].coords],
                color=color,
                weight=5,
                opacity=0.7,
            ).add_to(m)

        return m

    m = draw_path(m, path_shortest, color='#e74c3c')
    m = draw_path(m, path_practical, color='#0984e3')

    return m, path_shortest, path_practical, path_shortest_details, path_practical_details

# for getting images along the path
def sort_image_ids(image_id, source_osmid):
    source_coords = (nodes_gdf.loc[source_osmid, 'y'].item(), nodes_gdf.loc[source_osmid, 'x'].item()) # lat, lon
    image_coords = images_matches.loc[image_id, 'geometry'].coords[0][::-1]

    distance = great_circle(source_coords, image_coords)
    return distance.meters

def get_image_ids(path):
    image_ids = []
    osmid_to_image_id = images_matches.reset_index(drop=False).groupby('osmid').agg({ 'image_id': list })

    prev_image_ids = []

    for source_osmid, dest_osmid in nx.utils.pairwise(path):
        if (source_osmid, dest_osmid, 0) in roads_gdf.index:
            edge_osmid = roads_gdf.loc[(source_osmid, dest_osmid, 0), 'osmid']
        elif (dest_osmid, source_osmid, 0) in roads_gdf.index:
            edge_osmid = roads_gdf.loc[(dest_osmid, source_osmid, 0), 'osmid']
        else:
            print(f'Edge between {source_osmid} and {dest_osmid} not found')
            continue

        egde_osmid = edge_osmid.item()

        if edge_osmid in osmid_to_image_id.index:
            curr_image_ids = osmid_to_image_id.loc[edge_osmid].item()

            if curr_image_ids != prev_image_ids:
                curr_image_ids = sorted(curr_image_ids, key=lambda x: sort_image_ids(x, source_osmid))
                image_ids.extend([curr_image_ids[0], curr_image_ids[-1]])
                prev_images_ids = curr_image_ids

    return image_ids

def evenly_sample(input_list, n):
    if n <= 0:
        return input_list.copy()

    length = len(input_list)

    if n >= length:
        return input_list.copy()

    if n == 1:
        return [input_list[length // 2]]

    step = (length - 1) / (n - 1)
    indices = [int(round(i * step)) for i in range(n)]

    return [input_list[i] for i in indices]

def get_image_to_url(image_id):
    return image_to_url.loc[image_id, 'url']

if __name__ == '__main__':
    generate_map(5283414945, 3604556047).save('test_map.html')
