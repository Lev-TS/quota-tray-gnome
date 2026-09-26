import Cairo from 'cairo';
import {paintMeter} from './meter.js';

function paintedWidth(remaining, trackWidth) {
    const surface = new Cairo.ImageSurface(Cairo.Format.ARGB32, trackWidth, 7);
    const context = new Cairo.Context(surface);
    let fillWidth = null;
    const drawing = {
        newSubPath: () => context.newSubPath(),
        arc: (...args) => context.arc(...args),
        closePath: () => context.closePath(),
        setSourceRGB: (...args) => context.setSourceRGB(...args),
        fillPreserve: () => context.fillPreserve(),
        clip: () => context.clip(),
        rectangle: (x, y, width, height) => {
            fillWidth = width;
            context.rectangle(x, y, width, height);
        },
        fill: () => context.fill(),
        $dispose: () => context.$dispose(),
    };
    paintMeter({get_surface_size: () => [trackWidth, 7], get_context: () => drawing}, remaining, 'high');
    return fillWidth;
}

for (const trackWidth of [264, 396]) {
    for (const [remaining, expected] of [[100, trackWidth], [50, trackWidth / 2], [0, 0]]) {
        const actual = paintedWidth(remaining, trackWidth);
        if (actual !== expected)
            throw new Error(`${remaining}% of ${trackWidth}px: expected ${expected}px, got ${actual}px`);
    }
}
print('Meter rendering tests passed');
