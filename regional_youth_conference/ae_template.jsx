// Regional Youth Conference — logo animation builder for Adobe After Effects
// HOW TO USE: keep this file next to the "assets" folder, then in After Effects
// choose File > Scripts > Run Script File... and pick this file.
// It builds two fully keyframed comps (Vertical 1080x1920, Horizontal 1920x1080).
// Save the project afterwards (File > Save As) to get your .aep.
(function () {
    var D = /*DATA*/;
    var T = D.T;
    var k = D.pw / 1000; // motion unit, in layer pixels

    app.beginUndoGroup("Build RYC Logo Animation");
    if (!app.project) app.newProject();

    var dir = new File($.fileName).parent;
    var folder = app.project.items.addFolder("RYC Assets");
    function imp(file) {
        var f = new File(dir.fsName + "/assets/" + file);
        if (!f.exists) { alert("Missing asset: " + f.fsName + "\nKeep the 'assets' folder next to this script."); throw new Error("missing"); }
        var it = app.project.importFile(new ImportOptions(f));
        it.parentFolder = folder;
        return it;
    }
    var items = {};
    for (var i = 0; i < D.layers.length; i++) items[D.layers[i].name] = imp(D.layers[i].file);
    var sound = imp("RYC_sound.wav");

    // ---- keyframe helper: ei/eo = ease influence %, or -1 for linear ----
    function K(prop, t, v, ei, eo) {
        var idx = prop.addKey(t);
        prop.setValueAtKey(idx, v);
        var n = (prop.propertyValueType === PropertyValueType.TwoD_SPATIAL ||
                 prop.propertyValueType === PropertyValueType.ThreeD_SPATIAL) ? 1 :
                (v instanceof Array ? v.length : 1);
        var inA = [], outA = [];
        for (var j = 0; j < n; j++) {
            inA.push(new KeyframeEase(0, ei < 0 ? 0.1 : ei));
            outA.push(new KeyframeEase(0, eo < 0 ? 0.1 : eo));
        }
        prop.setTemporalEaseAtKey(idx, inA, outA);
        if (ei < 0 || eo < 0) {
            prop.setInterpolationTypeAtKey(idx,
                ei < 0 ? KeyframeInterpolationType.LINEAR : KeyframeInterpolationType.BEZIER,
                eo < 0 ? KeyframeInterpolationType.LINEAR : KeyframeInterpolationType.BEZIER);
        }
        return idx;
    }

    function makeComp(name, W, H, frac) {
        var comp = app.project.items.addComp(name, W, H, 1, 3, 30);
        var s = Math.min(W * frac / D.pw, H * 0.6 / D.ph) * 100;

        var bg = comp.layers.addSolid([1, 1, 1], "Background", W, H, 1);

        var ctrl = comp.layers.addNull(3);
        ctrl.name = "LOGO CONTROL (scale/move logo here)";
        ctrl.transform.anchorPoint.setValue([0, 0]);
        ctrl.transform.position.setValue([W / 2, H / 2]);
        ctrl.transform.scale.setValue([s, s]);

        var L = {};
        // add bottom-to-top so stacking matches the logo
        var order = ["Arch", "Arms", "Head"];
        for (var i = 0; i < D.layers.length; i++)
            if (D.layers[i].name.indexOf("Text_") === 0) order.push(D.layers[i].name);
        var piv = {};
        for (i = 0; i < D.layers.length; i++) piv[D.layers[i].name] = D.layers[i].pivot;

        for (i = 0; i < order.length; i++) {
            var nm = order[i];
            var ly = comp.layers.add(items[nm]);
            ly.parent = ctrl;
            var p = piv[nm];
            ly.transform.anchorPoint.setValue([p[0], p[1]]);
            ly.transform.scale.setValue([100, 100]);
            ly.transform.rotation.setValue(0);
            ly.transform.position.setValue([p[0] - D.pw / 2, p[1] - D.ph / 2]);
            L[nm] = { layer: ly, x: p[0] - D.pw / 2, y: p[1] - D.ph / 2 };
        }
        ctrl.moveToBeginning();
        bg.moveToEnd();

        // ---- ARCH: rises from below with overshoot, squashes on the hop ----
        var a = L["Arch"], tr = a.layer.transform;
        K(tr.position, T.arch, [a.x, a.y + 170 * k], 33, 70);
        K(tr.position, T.arch + 0.38, [a.x, a.y - 10 * k], 50, 50);
        K(tr.position, T.arch + 0.55, [a.x, a.y], 60, 33);
        K(tr.opacity, T.arch, 0, 33, 33);
        K(tr.opacity, T.arch + 0.22, 100, 33, 33);
        K(tr.scale, T.hop, [100, 100], 33, 50);
        K(tr.scale, T.hop + 0.25, [106, 94], 50, 50);
        K(tr.scale, T.hop + 0.5, [100, 100], 50, 33);

        // ---- ARMS: pop open from the middle, lift on the hop ----
        var u = L["Arms"]; tr = u.layer.transform;
        K(tr.scale, T.u, [25, 25], 33, 75);
        K(tr.scale, T.u + 0.38, [106, 106], 50, 50);
        K(tr.scale, T.u + 0.6, [100, 100], 60, 33);
        K(tr.scale, T.hop, [100, 100], 33, 50);
        K(tr.scale, T.hop + 0.25, [96, 108], 50, 50);
        K(tr.scale, T.hop + 0.5, [100, 100], 50, 33);
        K(tr.rotation, T.u, -25, 33, 75);
        K(tr.rotation, T.u + 0.6, 0, 70, 33);
        K(tr.opacity, T.u, 0, 33, 33);
        K(tr.opacity, T.u + 0.2, 100, 33, 33);
        K(tr.position, T.hop, [u.x, u.y], 33, 50);
        K(tr.position, T.hop + 0.25, [u.x, u.y - 22 * k], 60, 60);
        K(tr.position, T.hop + 0.5, [u.x, u.y], 50, 33);

        // ---- HEAD: drops in with a 3-step bounce + squash, then jumps ----
        var h = L["Head"]; tr = h.layer.transform;
        var t0 = T.head, d = T.dhead;
        var hits = [1 / 2.75, 2 / 2.75, 2.5 / 2.75];
        var peaks = [[1.5 / 2.75, 0.25], [2.25 / 2.75, 0.0625], [2.625 / 2.75, 0.015625]];
        K(tr.position, t0, [h.x, h.y - 330 * k], 33, 60);
        K(tr.position, t0 + hits[0] * d, [h.x, h.y], -1, -1);
        K(tr.position, t0 + peaks[0][0] * d, [h.x, h.y - 330 * k * peaks[0][1]], 60, 60);
        K(tr.position, t0 + hits[1] * d, [h.x, h.y], -1, -1);
        K(tr.position, t0 + peaks[1][0] * d, [h.x, h.y - 330 * k * peaks[1][1]], 60, 60);
        K(tr.position, t0 + hits[2] * d, [h.x, h.y], -1, -1);
        K(tr.position, t0 + peaks[2][0] * d, [h.x, h.y - 330 * k * peaks[2][1]], 60, 60);
        K(tr.position, t0 + d, [h.x, h.y], 50, 33);
        K(tr.position, T.hop - 0.05, [h.x, h.y], 33, 60);
        K(tr.position, T.hop + 0.25, [h.x, h.y - 70 * k], 60, 60);
        K(tr.position, T.hop + 0.55, [h.x, h.y], 60, 33);
        K(tr.opacity, t0, 0, 33, 33);
        K(tr.opacity, t0 + 0.1, 100, 33, 33);
        var sq = [0.78, 0.89, 0.93];
        for (var b = 0; b < 3; b++) {
            var th = t0 + hits[b] * d;
            K(tr.scale, th - 0.035, [100, 100], 40, 40);
            K(tr.scale, th, [100 / Math.sqrt(sq[b]), 100 * sq[b]], 40, 40);
            K(tr.scale, th + 0.035, [100, 100], 40, 40);
        }

        // ---- TEXT: lines slide in from the right, staggered ----
        var li = 0;
        for (var oi = 3; oi < order.length; oi++) {
            var tl = L[order[oi]], tt = T.text + li * 0.13;
            tr = tl.layer.transform;
            K(tr.position, tt, [tl.x + 90 * k, tl.y], 33, 80);
            K(tr.position, tt + 0.55, [tl.x, tl.y], 90, 33);
            K(tr.opacity, tt, 0, 33, 80);
            K(tr.opacity, tt + 0.55, 100, 90, 33);
            li++;
        }

        var snd = comp.layers.add(sound);
        snd.name = "Sound (whoosh, pops, ticks, chime)";
        snd.moveToEnd();
        bg.moveToEnd();
        return comp;
    }

    var v = makeComp("RYC Logo - Vertical 1080x1920", 1080, 1920, 0.8);
    makeComp("RYC Logo - Horizontal 1920x1080", 1920, 1080, 0.55);
    v.openInViewer();
    app.endUndoGroup();
    alert("Done! Two comps were created in your Project panel.\nUse File > Save As to keep your .aep.");
})();
