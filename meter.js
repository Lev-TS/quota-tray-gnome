export function paintMeter(area, remaining, tone) {
    const [width, height] = area.get_surface_size();
    const radius = Math.min(width, height) / 2;
    const colors = {
        high: [141, 213, 188],
        medium: [240, 198, 126],
        low: [239, 157, 145],
    };
    const cr = area.get_context();
    try {
        cr.newSubPath();
        cr.arc(width - radius, radius, radius, -Math.PI / 2, 0);
        cr.arc(width - radius, height - radius, radius, 0, Math.PI / 2);
        cr.arc(radius, height - radius, radius, Math.PI / 2, Math.PI);
        cr.arc(radius, radius, radius, Math.PI, 3 * Math.PI / 2);
        cr.closePath();
        cr.setSourceRGB(54 / 255, 61 / 255, 71 / 255);
        cr.fillPreserve();
        cr.clip();
        cr.rectangle(0, 0, width * remaining / 100, height);
        cr.setSourceRGB(...colors[tone].map(value => value / 255));
        cr.fill();
    } finally {
        cr.$dispose();
    }
}
