export type Vector3Tuple = [number, number, number];

export type AssetType =
  | "glb"
  | "gltf"
  | "ply"
  | "ply_mesh"
  | "gaussian_splat"
  | "navigation_grid"
  | "collider_geometry"
  | "camera_poses"
  | "poi_metadata"
  | "texture"
  | "image";

export interface SceneAsset {
  id: string;
  type: AssetType;
  path: string;
  role: "primary_visual" | "diagnostic" | "navigation" | "metadata" | "texture";
  mime_type: string;
  required: boolean;
  visible_by_default: boolean;
}

export interface SceneSummary {
  scene_id: string;
  scene_name: string;
  description: string;
  processing_status: string;
  synthetic_demo: boolean;
  asset_types: AssetType[];
  primary_asset_type?: string | null;
  backend?: string | null;
  metric_scale_status?: string | null;
  created_at?: string | null;
  manifest_url: string;
  thumbnail_path?: string | null;
}

export type CameraMode = "first-person" | "orbit" | "overview";
export type QualityPreset = "low" | "balanced" | "high";

export interface CameraTelemetry {
  position: Vector3Tuple;
  yaw: number;
  mode: CameraMode;
  near?: number;
  far?: number;
  fov?: number;
  webglStatus?: string;
  webglRenderer?: string;
  visibleObjects?: number;
}

export interface RenderMetrics {
  fps: number | null;
  frameTimeMs: number | null;
  drawCalls: number | null;
  triangles: number | null;
  points: number | null;
  geometries?: number | null;
  textures?: number | null;
}

export interface ViewerPackValidation {
  is_valid: boolean;
  scene_id: string;
  scene_type: string;
  visual_asset_path: string;
  geometry_format: string;
  point_count: number;
  triangle_count: number;
  bounding_box_min: Vector3Tuple;
  bounding_box_max: Vector3Tuple;
  span: number;
  center: Vector3Tuple;
  camera_pose_count: number;
  errors: string[];
  warnings: string[];
}

export interface UnifiedQualityReport {
  scene_id: string;
  pipeline: string;
  status: string;
  confidence_score: number;
  metric_scale_status: string;
  geometry_summary: {
    point_count: number;
    triangle_count: number;
    span: number;
    bounding_box_min: Vector3Tuple;
    bounding_box_max: Vector3Tuple;
    center: Vector3Tuple;
    camera_pose_count: number;
    geometry_format: string;
    is_valid: boolean;
  };
  input_quality: Record<string, unknown>;
  reconstruction_metrics: Record<string, unknown>;
  limitations: string[];
  recommendations: string[];
}

export interface SceneManifest {
  schema_version: "1.0.0";
  scene_id: string;
  scene_name: string;
  description: string;
  synthetic_demo: boolean;
  processing_status: "completed" | "demonstration" | "pending" | "failed";
  coordinate_system: {
    handedness: "right";
    up_axis: "Y";
    forward_axis: "-Z";
    source_convention: string;
    source_to_scene_matrix_row_major: number[];
  };
  units: {
    name: "meter" | "scene_unit";
    metric_scale_status: "known" | "estimated" | "arbitrary";
    meters_per_unit: number | null;
  };
  origin: Vector3Tuple;
  bounding_box: { minimum: Vector3Tuple; maximum: Vector3Tuple };
  reconstruction: {
    backend: string;
    backend_version: string | null;
    source: "reconstruction" | "synthetic" | "imported";
    status: string;
    metric_scale_calibrated: boolean;
  };
  assets: SceneAsset[];
  camera_metadata: { pose_asset_id: string | null; pose_convention: string };
  navigation: {
    enabled: boolean;
    spawn_position: Vector3Tuple;
    spawn_yaw_degrees: number;
    camera_height: number;
    movement_speed: number;
    collision_radius: number;
    collider_asset_id: string | null;
    grid_asset_id: string | null;
    zones: string[];
  };
  poi_metadata: { asset_id: string | null; count: number };
  viewer: {
    background: string;
    ambient_light_intensity: number;
    directional_light_intensity: number;
    point_size: number;
    is_2_5d?: boolean;
    source_camera_position?: Vector3Tuple;
    source_camera_look_at?: Vector3Tuple;
    source_camera_fov?: number;
  };
}

export interface Collider {
  id: string;
  minimum: Vector3Tuple;
  maximum: Vector3Tuple;
}

export interface ColliderDocument {
  schema_version: "1.0.0";
  coordinate_system: string;
  walkable_bounds: { minimum: Vector3Tuple; maximum: Vector3Tuple };
  colliders: Collider[];
}

export interface POI {
  id: string;
  name: string;
  category: string;
  description: string;
  aliases: string[];
  position: Vector3Tuple;
  arrival_points: Vector3Tuple[];
  floor_id: string;
  bounds: [Vector3Tuple, Vector3Tuple] | null;
  zone: string | null;
}

export interface NavigationGrid {
  schema_version: "1.0.0";
  version: string;
  coordinate_system: "SpatialForge right-handed Y-up";
  floor_id: string;
  floor_y: number;
  origin: Vector3Tuple;
  resolution: number;
  width: number;
  height: number;
  connectivity: 4 | 8;
  cells: string[];
  unit: "meter" | "scene_unit";
  metric_scale_status: "known" | "estimated" | "arbitrary";
}

export interface RouteResult {
  status: "completed";
  waypoints: Vector3Tuple[];
  route_length: number;
  distance_units: "meter" | "scene_unit";
  navigation_grid_version: string;
  destination: { poi_id: string | null; name: string | null; position: Vector3Tuple };
}

export interface PipelineStage {
  name: string;
  status: string;
  current_stage?: string | null;
  details: Record<string, unknown>;
}

export interface PipelineJob {
  scene_id: string;
  status: string;
  current_stage: string;
  stages: PipelineStage[];
  error: string | null;
  has_original_input: boolean;
  has_viewer_manifest: boolean;
  capture_mode?: "photo_set" | "video" | "single_photo" | null;
}
