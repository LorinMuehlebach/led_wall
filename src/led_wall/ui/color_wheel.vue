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