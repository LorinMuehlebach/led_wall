<template>
  <input type="text" data-wheelcolorpicker>
</template>

<script>
export default {
  mounted() {
    let element = this.$el;
    console.log(element);
    //element = $(element).find("input")[0];
    console.log(element);
    let vue_element = this;
    $(element).on('colorchange', function() {
        let hex = $(this).wheelColorPicker('getValue');
        vue_element.$emit("colorchange", hex)
        console.log(hex);
    }); 

    $(element).on('change', function(e) {
        let hex = $(this).wheelColorPicker('getValue');
        vue_element.$emit("change", hex);
    }); 
  },
  props: {
    options: Object,
  },
  methods: {
    setColor(color) {
        let element = this.$el;
        $(element).wheelColorPicker( 'setColor', color );
    }
  }
};
</script>