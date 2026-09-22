const basePath = "babybuddy/static/babybuddy/";

const config = {
  basePath: basePath,
  extrasConfig: {
    fonts: {
      dest: basePath + "font/",
      files: "babybuddy/static_src/fontello/font/*",
    },
    images: {
      dest: basePath + "img/",
      files: "**/static_src/img/**/*",
    },
    logo: {
      dest: basePath + "logo/",
      files: "babybuddy/static_src/logo/**/*",
    },
    root: {
      dest: basePath + "root/",
      files: "babybuddy/static_src/root/*",
    },
  },
  glyphFontConfig: {
    configFile: "babybuddy/static_src/fontello/config.json",
    dest: "babybuddy/static_src/fontello",
  },
  scriptsConfig: {
    dest: basePath + "js/",
    vendor: [
      "node_modules/pulltorefreshjs/dist/index.umd.js",
      "node_modules/jquery/dist/jquery.js",
      "node_modules/@popperjs/core/dist/umd/popper.js",
      "node_modules/bootstrap/dist/js/bootstrap.js",
      "node_modules/masonry-layout/dist/masonry.pkgd.js",
    ],
    graph: [
      "node_modules/plotly.js-cartesian-dist/plotly-cartesian.js",
      "node_modules/plotly.js-locales/ca.js",
      "node_modules/plotly.js-locales/cs.js",
      "node_modules/plotly.js-locales/de.js",
      "node_modules/plotly.js-locales/da.js",
      "node_modules/plotly.js-locales/es.js",
      "node_modules/plotly.js-locales/fi.js",
      "node_modules/plotly.js-locales/fr.js",
      "node_modules/plotly.js-locales/he.js",
      "node_modules/plotly.js-locales/hr.js",
      "node_modules/plotly.js-locales/hu.js",
      "node_modules/plotly.js-locales/it.js",
      "node_modules/plotly.js-locales/ko.js",
      "node_modules/plotly.js-locales/ja.js",
      "node_modules/plotly.js-locales/no.js",
      "node_modules/plotly.js-locales/nl.js",
      "node_modules/plotly.js-locales/pl.js",
      "node_modules/plotly.js-locales/pt-br.js",
      "node_modules/plotly.js-locales/pt-pt.js",
      "node_modules/plotly.js-locales/ru.js",
      "node_modules/plotly.js-locales/sr.js",
      "node_modules/plotly.js-locales/sv.js",
      "node_modules/plotly.js-locales/tr.js",
      "node_modules/plotly.js-locales/uk.js",
      "node_modules/plotly.js-locales/zh-cn.js",
      "node_modules/plotly.js-locales/zh-hk.js",
      "node_modules/plotly.js-locales/zh-tw.js",
    ],
    app: [
      "babybuddy/static_src/js/babybuddy.js",
      "core/static_src/js/*.js",
      "dashboard/static_src/js/*.js",
      "reports/static_src/js/*.js",
    ],
    tags_editor: ["babybuddy/static_src/js/tags_editor.js"],
  },
  stylesConfig: {
    dest: basePath + "css/",
    app: "babybuddy/static_src/scss/babybuddy.scss",
    ignore: ["babybuddy.scss"],
  },
  testsConfig: {
    isolated: ["babybuddy.tests.tests_views.ViewsTestCase.test_password_reset"],
  },
  watchConfig: {
    scriptsGlob: ["*/static_src/js/**/*.js", "!babybuddy/static/js/"],
    stylesGlob: ["*/static_src/scss/**/*.scss"],
  },
};

export default config;
