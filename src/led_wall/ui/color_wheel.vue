<template>
  <div ref="container">
    <input ref="input" type="text">
  </div>
</template>

<script>
export default {
  mounted() {
    let input = this.$refs.input;
    let vue_element = this;

    // Manually initialize the plugin with options passed from Python
    let opts = this.options || {};
    $(input).wheelColorPicker(opts);

    // After the plugin renders, fix sizing and zoom in $nextTick.
    // Strategy:
    //   a) Directly resize widget internals to desired size (no zoom/transform
    //      for sizing — those break the plugin's coordinate math).
    //   b) Apply zoom: 1/ancestorZoom ONLY for coordinate fix (makes
    //      totalZoom = 1 so pageX and offset() use the same units).
    this.$nextTick(() => {
        let widget = $(input).closest('.jQWCP-wWidget');
        if (!widget.length) return;

        // --- a) Resize widget internals proportionally ---
        if (this.widget_size) {
            let naturalH = widget.height() || 180;
            let naturalW = widget.width() || 250;
            let scale = this.widget_size / naturalH;

            // Scale each visible child (wheel, sliders, preview)
            widget.find('.jQWCP-wWheel, .jQWCP-slider-wrapper, .jQWCP-wPreview')
                  .not('.hidden').each(function() {
                let $el = $(this);
                let w = $el.width();
                let h = $el.height();
                // Halve the width of slider bars (brightness etc.)
                let wScale = $el.hasClass('jQWCP-slider-wrapper') ? scale * 0.5 : scale;
                $el.css({
                    width:  Math.round(w * wScale) + 'px',
                    height: Math.round(h * scale) + 'px'
                });
            });

            // Resize the widget container to fit the scaled children
            let totalW = 0;
            widget.find('.jQWCP-wWheel, .jQWCP-slider-wrapper, .jQWCP-wPreview')
                  .not('.hidden').each(function() {
                let $el = $(this);
                totalW += $el.outerWidth(true);
            });
            widget.css({
                width:  totalW + 'px',
                height: Math.round(naturalH * scale) + 'px'
            });

            // Redraw canvases at new dimensions
            let instance = $(input).data('jQWCP.instance');
            if (instance) {
                instance.redrawSliders(true);
                instance.updateSliders();
            }
        }

        // --- b) Compensate ancestor CSS zoom for coordinate accuracy ---
        // The plugin mixes pageX (viewport px) with width()/height()
        // (CSS px). These only match when total zoom = 1.
        let ancestorZoom = 1;
        let el = this.$refs.container;
        while (el) {
            let z = parseFloat(window.getComputedStyle(el).zoom);
            if (!isNaN(z)) ancestorZoom *= z;
            el = el.parentElement;
        }
        if (Math.abs(ancestorZoom - 1) > 0.001) {
            widget.css('zoom', 1 / ancestorZoom);
        }
    });

    // Bind events after initialization
    $(input).on('colorchange', function() {
        let hex = $(this).wheelColorPicker('getValue');
        vue_element.$emit("colorchange", hex);
    });

    $(input).on('change', function(e) {
        let hex = $(this).wheelColorPicker('getValue');
        vue_element.$emit("change", hex);
    });

    $(input).on('sliderdown', function() {
        vue_element.$emit("dragstart");
    });

    $(input).on('sliderup', function() {
        let hex = $(this).wheelColorPicker('getValue');
        vue_element.$emit("dragend", hex);
    });
  },
  props: {
    options: Object,
    widget_size: Number,
  },
  methods: {
    setColor(color) {
        let input = this.$refs.input;
        $(input).wheelColorPicker('setColor', color);
    }
  }
};
</script>

<style>
/* Override float-based layout with flexbox so it works inside NiceGUI/Quasar flex containers */
.jQWCP-wWidget {
    display: flex !important;
    flex-wrap: nowrap;
    align-items: flex-start;
    box-sizing: content-box;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
}

.jQWCP-wWidget.jQWCP-block {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

.jQWCP-wWheel,
.jQWCP-slider-wrapper,
.jQWCP-wPreview {
    float: none !important;
    flex-shrink: 0;
}
</style>