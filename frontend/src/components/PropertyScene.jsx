import { useEffect, useRef } from "react";
import * as THREE from "three";

// Azimuth, elevation, target height, and horizontal framing in world units.
const VIEWS = [
  [-34, 22, 1.22, -.85],
  [-13, 31, 1.28, -.32],
  [16, 71, 1.82, .18],
  [39, 48, 1.15, .68],
];

const smoothstep = t => t * t * (3 - 2 * t);

function model(scene) {
  const shell = new THREE.Group();
  const roof = new THREE.Group();
  const interior = new THREE.Group();
  const building = new THREE.Group();
  building.add(shell, roof, interior);
  scene.add(building);

  const structure = new THREE.MeshStandardMaterial({ color: 0x4e504a, roughness: .84 });
  const base = new THREE.MeshStandardMaterial({ color: 0x30322e, roughness: .95 });
  const window = new THREE.MeshStandardMaterial({ color: 0x181a17, roughness: .55 });
  const accent = new THREE.MeshStandardMaterial({ color: 0xf39568, roughness: .76 });
  const edges = new THREE.LineBasicMaterial({ color: 0x8a8980 });
  const dims = new Map();

  function block(group, size, position, material, outline = true) {
    const key = size.join(",");
    if (!dims.has(key)) {
      const geometry = new THREE.BoxGeometry(...size);
      dims.set(key, [geometry, new THREE.EdgesGeometry(geometry)]);
    }
    const [geometry, edgeGeometry] = dims.get(key);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(...position);
    if (outline) mesh.add(new THREE.LineSegments(edgeGeometry, edges));
    group.add(mesh);
  }

  block(scene, [9.2, .16, 6.65], [0, -.08, 0], base);
  for (const y of [.12, .81, 1.5]) {
    block(shell, [6.6, .6, 4.6], [0, y + .3, 0], structure);
    block(shell, [6.74, .085, 4.74], [0, y, 0], base);
  }
  block(roof, [6.8, .15, 4.8], [0, 2.25, 0], structure);
  for (const y of [.55, 1.17, 1.79]) {
    for (let x = -2.7; x <= 2.8; x += .77) {
      block(shell, [.48, .28, .024], [x, y, 2.31], window, false);
      block(shell, [.48, .28, .024], [x, y, -2.31], window, false);
    }
    for (let z = -1.8; z <= 1.9; z += .69) {
      block(shell, [.024, .28, .43], [3.31, y, z], window, false);
      block(shell, [.024, .28, .43], [-3.31, y, z], window, false);
    }
  }
  for (const z of [-1.45, 1.45]) block(roof, [6.65, .045, .045], [0, 2.35, z * 1.59], accent, false);
  for (const x of [-3.31, 3.31]) block(roof, [.045, .045, 4.64], [x, 2.35, 0], accent, false);
  for (const z of [-1.2, 1.2]) {
    for (const x of [-2.35, -.8, .8, 2.35]) block(roof, [.61, .22, .44], [x, 2.44, z], base);
  }
  block(interior, [6.65, .12, 4.65], [0, .07, 0], structure);
  block(interior, [6.55, .05, .65], [0, .15, 0], accent, false);
  for (const z of [-2.3, -.38, .38, 2.3]) block(interior, [6.65, .45, .055], [0, .35, z], structure);
  for (const x of [-3.3, -1.65, 0, 1.65, 3.3]) {
    for (const z of [-1.35, 1.35]) block(interior, [.055, .45, 1.95], [x, .35, z], structure);
  }
  const grid = new THREE.GridHelper(19, 25, 0x3e4039, 0x292b27);
  grid.position.y = -.18;
  scene.add(grid);
  return {
    show(progress, x) {
      const open = smoothstep(THREE.MathUtils.clamp((progress - 2) / .78, 0, 1));
      building.position.x = x;
      // Separate the shell from the cutaway before lifting the roof off to the right.
      shell.scale.y = 1 - open * .96;
      shell.visible = open < .97;
      interior.position.y = -1.2 * (1 - open);
      interior.visible = open > .14;
      roof.position.set(open * 4.4, open * 1.35, -open * 2.3);
      accent.emissive.setHex(progress >= 1.6 ? 0x743a24 : 0x24130c);
    },
    dispose() {
      for (const pair of dims.values()) pair.forEach(geometry => geometry.dispose());
      [structure, base, window, accent, edges, grid.material, grid.geometry].forEach(resource => resource.dispose());
    },
  };
}

export default function PropertyScene({ progress, onReady }) {
  const host = useRef(null);

  useEffect(() => {
    const node = host.current;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    } catch {
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.6));
    node.append(renderer.domElement);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xfff6e7, 0x5a5c55, 2));
    const light = new THREE.DirectionalLight(0xffeee1, 2.1);
    light.position.set(-4, 9, 7);
    scene.add(light);
    const property = model(scene);
    const camera = new THREE.OrthographicCamera();
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    let current = progress.current.value;
    let previousTime;
    let frame = 0;
    let contextLost = false;

    function schedule() {
      if (!frame && !contextLost) frame = requestAnimationFrame(render);
    }

    function render(time) {
      frame = 0;
      const target = progress.current.value;
      const dt = Math.min((time - (previousTime ?? time - 16)) / 1000, .05);
      previousTime = time;
      current = motion.matches || progress.current.instant
        ? target
        : THREE.MathUtils.damp(current, target, 12, dt);
      const remaining = Math.abs(current - target);
      if (remaining < .002) current = target;
      const start = Math.min(Math.floor(current), VIEWS.length - 2);
      const fraction = smoothstep(current - start);
      const [azimuth, elevation, height, x] = VIEWS[start].map((value, i) =>
        THREE.MathUtils.lerp(value, VIEWS[start + 1][i], fraction));
      const yaw = THREE.MathUtils.degToRad(azimuth);
      const pitch = THREE.MathUtils.degToRad(elevation);
      const radius = 13;
      camera.position.set(
        radius * Math.sin(yaw) * Math.cos(pitch),
        height + radius * Math.sin(pitch),
        radius * Math.cos(yaw) * Math.cos(pitch),
      );
      camera.zoom = 1 - smoothstep(Math.max(0, current - 2)) * .21;
      camera.updateProjectionMatrix();
      camera.lookAt(0, height, 0);
      property.show(current, x);
      renderer.render(scene, camera);
      if (remaining >= .002) schedule();
      else previousTime = undefined;
    }

    function resize() {
      const width = Math.max(node.clientWidth, 1);
      const height = Math.max(node.clientHeight, 1);
      const aspect = width / height;
      const half = Math.max(3.85, 6.25 / aspect);
      Object.assign(camera, { left: -half * aspect, right: half * aspect, top: half, bottom: -half, near: .1, far: 65 });
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      schedule();
    }

    const onLost = event => {
      event.preventDefault();
      contextLost = true;
      cancelAnimationFrame(frame);
      frame = 0;
      onReady(false);
    };
    const onRestored = () => {
      contextLost = false;
      schedule();
      onReady(true);
    };
    const channel = progress.current;
    channel.draw = schedule;
    renderer.domElement.addEventListener("webglcontextlost", onLost);
    renderer.domElement.addEventListener("webglcontextrestored", onRestored);
    const observer = new ResizeObserver(resize);
    observer.observe(node);
    motion.addEventListener("change", schedule);
    resize();
    onReady(true);
    return () => {
      channel.draw = null;
      observer.disconnect();
      motion.removeEventListener("change", schedule);
      cancelAnimationFrame(frame);
      renderer.domElement.removeEventListener("webglcontextlost", onLost);
      renderer.domElement.removeEventListener("webglcontextrestored", onRestored);
      property.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [onReady, progress]);

  return <div className="property-scene" ref={host} aria-hidden="true" />;
}
