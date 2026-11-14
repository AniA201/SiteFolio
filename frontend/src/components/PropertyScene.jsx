import { useEffect, useRef } from "react";
import * as THREE from "three";

const VIEWS = [
  { camera: [8, 5, 10], target: [0, 1.1, 0] },
  { camera: [-9, 4, 9], target: [0, 1.2, 0] },
  { camera: [0, 13, 5], target: [0, 2.1, 0] },
  { camera: [7, 11, 7], target: [0, 1, 0] },
];

function model(scene) {
  const shell = new THREE.Group();
  const roof = new THREE.Group();
  const interior = new THREE.Group();
  scene.add(shell, roof, interior);

  const structure = new THREE.MeshStandardMaterial({ color: 0x4e504a, roughness: .84 });
  const base = new THREE.MeshStandardMaterial({ color: 0x30322e, roughness: .95 });
  const window = new THREE.MeshStandardMaterial({ color: 0x181a17, roughness: .55 });
  const accent = new THREE.MeshStandardMaterial({ color: 0xf28a5d, roughness: .76 });
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

  block(scene, [9, .16, 6.6], [0, -.08, 0], base);
  block(shell, [6.6, 2.2, 4.6], [0, 1.1, 0], structure);
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
  const grid = new THREE.GridHelper(25, 34, 0x45473f, 0x2b2d28);
  grid.position.y = -.18;
  scene.add(grid);
  return {
    show(stage) {
      shell.visible = roof.visible = stage !== 3;
      interior.visible = stage === 3;
      accent.emissive.setHex(stage >= 2 ? 0x823d25 : 0x160c07);
    },
    dispose() {
      for (const pair of dims.values()) pair.forEach(geometry => geometry.dispose());
      [structure, base, window, accent, edges, grid.material, grid.geometry].forEach(resource => resource.dispose());
    },
  };
}

export default function PropertyScene({ stage, onReady }) {
  const host = useRef(null);
  const update = useRef(null);

  useEffect(() => {
    const node = host.current;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    } catch {
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.7));
    node.append(renderer.domElement);
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xfff6e7, 0x5a5c55, 2));
    const light = new THREE.DirectionalLight(0xffeee1, 2.1);
    light.position.set(-4, 9, 7);
    scene.add(light);
    const property = model(scene);
    const camera = new THREE.OrthographicCamera();
    const cameraTarget = new THREE.Vector3();
    const lookTarget = new THREE.Vector3();
    const look = new THREE.Vector3();
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let previousTime;
    let shownStage = 0;
    let nextStage = 0;
    let initialized = false;

    function render(time) {
      frame = 0;
      const dt = Math.min((time - (previousTime ?? time - 16)) / 1000, .06);
      const strength = motion.matches ? 1 : 1 - Math.exp(-dt * 7);
      previousTime = time;
      camera.position.lerp(cameraTarget, strength);
      look.lerp(lookTarget, strength);
      if (nextStage !== shownStage && (motion.matches || camera.position.distanceTo(cameraTarget) < 3.6)) {
        shownStage = nextStage;
        property.show(shownStage);
      }
      camera.lookAt(look);
      renderer.render(scene, camera);
      if (camera.position.distanceToSquared(cameraTarget) + look.distanceToSquared(lookTarget) > .0005) schedule();
    }

    function schedule() {
      if (!frame) frame = requestAnimationFrame(render);
    }

    function resize() {
      const width = Math.max(node.clientWidth, 1);
      const height = Math.max(node.clientHeight, 1);
      const aspect = width / height;
      const half = Math.max(3.65, 5.8 / aspect);
      Object.assign(camera, { left: -half * aspect, right: half * aspect, top: half, bottom: -half, near: .1, far: 65 });
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
      schedule();
    }

    update.current = index => {
      const view = VIEWS[index];
      nextStage = index;
      cameraTarget.set(...view.camera);
      lookTarget.set(...view.target);
      if (!initialized) {
        initialized = true;
        camera.position.copy(cameraTarget);
        look.copy(lookTarget);
        shownStage = index;
        property.show(index);
      }
      previousTime = undefined;
      schedule();
    };

    const onLost = event => {
      event.preventDefault();
      cancelAnimationFrame(frame);
      frame = 0;
      onReady(false);
    };
    const onRestored = () => { schedule(); onReady(true); };
    renderer.domElement.addEventListener("webglcontextlost", onLost);
    renderer.domElement.addEventListener("webglcontextrestored", onRestored);
    const observer = new ResizeObserver(resize);
    observer.observe(node);
    motion.addEventListener("change", schedule);
    resize();
    onReady(true);
    return () => {
      observer.disconnect();
      motion.removeEventListener("change", schedule);
      cancelAnimationFrame(frame);
      renderer.domElement.removeEventListener("webglcontextlost", onLost);
      renderer.domElement.removeEventListener("webglcontextrestored", onRestored);
      property.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [onReady]);

  useEffect(() => { update.current?.(stage); }, [stage]);

  return <div className="property-scene" ref={host} aria-hidden="true" />;
}
