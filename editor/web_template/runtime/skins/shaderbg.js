/*
 * skins/shaderbg.js — sfondo a fragment-shader in WebGL puro (niente Three.js,
 * nessuna CDN: funziona da file://). E' OPZIONALE e additivo: lo skin lo monta
 * solo se background.mode === "shader", c'e' WebGL e non e' attiva la reduced-
 * motion; in caso contrario resta lo sfondo CSS dello skin (fallback verificato).
 *
 * ShaderBG.create(container, name) -> { destroy() }  (o null se non disponibile).
 */

window.ShaderBG = (function () {
  var VS = "attribute vec2 p;void main(){gl_Position=vec4(p,0.0,1.0);}";

  // Sintetizzatore synthwave: cielo viola, sole a bande, griglia neon in
  // prospettiva che scorre, vignetta e scanline.
  var SYNTHWAVE = [
    "precision mediump float;",
    "uniform vec2 u_res; uniform float u_time;",
    "void main(){",
    "  vec2 uv = gl_FragCoord.xy / u_res.xy;",
    "  vec2 p = uv*2.0 - 1.0; p.x *= u_res.x / u_res.y;",
    "  float t = u_time;",
    "  vec3 col;",
    "  if(p.y > 0.0){",
    "    col = mix(vec3(0.10,0.02,0.18), vec3(0.02,0.01,0.07), p.y);",
    "    vec2 s = p - vec2(0.0,0.18); float d = length(s);",
    "    float sun = smoothstep(0.40,0.38,d);",
    "    vec3 sunCol = mix(vec3(1.0,0.85,0.2), vec3(1.0,0.2,0.5), clamp((s.y+0.4)/0.8,0.0,1.0));",
    "    float bands = step(0.0, sin(p.y*70.0 - 1.0)); bands = max(bands, step(p.y,0.02));",
    "    col = mix(col, sunCol, sun*bands);",
    "    col += vec3(1.0,0.1,0.6)*pow(max(0.0,1.0-p.y*6.0),3.0)*0.5;",
    "  } else {",
    "    float z = 1.0/(-p.y + 0.06);",
    "    float gx = p.x*z*0.5; float gy = z*0.5 - t*0.8;",
    "    float fx = abs(fract(gx)-0.5); float fy = abs(fract(gy)-0.5);",
    "    float line = max(smoothstep(0.045,0.0,fx), smoothstep(0.045,0.0,fy));",
    "    float fade = clamp(1.0 - z*0.04, 0.0, 1.0);",
    "    vec3 neon = mix(vec3(0.0,1.0,1.0), vec3(1.0,0.0,1.0), uv.x);",
    "    col = vec3(0.02,0.01,0.06) + neon*line*fade*1.3;",
    "    col += vec3(1.0,0.1,0.6)*pow(max(0.0,1.0+p.y*6.0),3.0)*0.25;",
    "  }",
    "  col *= 0.85 + 0.15*sin(gl_FragCoord.y*2.0);",
    "  col *= 1.0 - 0.3*length(p*vec2(0.5,0.6));",
    "  gl_FragColor = vec4(clamp(col,0.0,1.0),1.0);",
    "}"
  ].join("\n");

  var SHADERS = { synthwave: SYNTHWAVE };

  function compile(gl, type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn("ShaderBG compile:", gl.getShaderInfoLog(s));
      return null;
    }
    return s;
  }

  function create(container, name) {
    var src = SHADERS[name] || SHADERS.synthwave;
    var canvas = document.createElement("canvas");
    canvas.className = "shader-bg";
    canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block";
    var gl = null;
    var opts = { antialias: true, preserveDrawingBuffer: true, premultipliedAlpha: false };
    try { gl = canvas.getContext("webgl", opts) || canvas.getContext("experimental-webgl", opts); } catch (e) {}
    if (!gl) return null;

    var v = compile(gl, gl.VERTEX_SHADER, VS);
    var f = compile(gl, gl.FRAGMENT_SHADER, src);
    if (!v || !f) return null;
    var prog = gl.createProgram();
    gl.attachShader(prog, v); gl.attachShader(prog, f); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.warn("ShaderBG link:", gl.getProgramInfoLog(prog));
      return null;
    }
    gl.useProgram(prog);
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    var uRes = gl.getUniformLocation(prog, "u_res");
    var uTime = gl.getUniformLocation(prog, "u_time");

    container.appendChild(canvas);
    var alive = true, raf = 0, t0 = null;

    function resize() {
      // .menu-bg e' fixed a tutto schermo: dimensiona dal viewport (robusto anche
      // se l'overlay e' ancora display:none al momento del mount).
      var dpr = Math.min(2, window.devicePixelRatio || 1);
      var w = window.innerWidth || container.clientWidth || 800;
      var h = window.innerHeight || container.clientHeight || 600;
      canvas.width = Math.max(2, Math.round(w * dpr * 0.7));
      canvas.height = Math.max(2, Math.round(h * dpr * 0.7));
      gl.viewport(0, 0, canvas.width, canvas.height);
    }
    function draw(t) {
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uTime, t);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    function frame(ts) {
      if (!alive) return;
      if (t0 === null) t0 = ts;
      draw((ts - t0) / 1000);
      raf = requestAnimationFrame(frame);
    }
    var onResize = function () { resize(); draw(0); };
    resize();
    draw(0);  // primo frame immediato (non dipende dal rAF)
    window.addEventListener("resize", onResize);
    raf = requestAnimationFrame(frame);

    return {
      resize: function () { resize(); draw(0); },
      render: draw,
      destroy: function () {
        alive = false;
        cancelAnimationFrame(raf);
        window.removeEventListener("resize", onResize);
        try {
          var ext = gl.getExtension("WEBGL_lose_context");
          if (ext) ext.loseContext();
        } catch (e) {}
        if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
      }
    };
  }

  return { create: create, SHADERS: SHADERS };
})();
