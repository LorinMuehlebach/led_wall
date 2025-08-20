<template>
  <div>
    custom vue
  </div>
</template>

<script>
import _ from 'lodash';

export default {
  created() {
   console.log(_.isEmpty() ? 'Lodash is available here!' : 'Uh oh..');
  }
} 
</script>