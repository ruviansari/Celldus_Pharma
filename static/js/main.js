/** ==========================================================================================

  Project :   Labostica - Responsive Multi-purpose HTML5 Template
  Author :    Themetechmount
  Version :   Bootstrap 5.3.3

========================================================================================== */


/** ===============

01. Preloader
02. header_search
03. Datetimepicker
04. Fixed-header
05. Menu
06. Number rotator
07. Skillbar
08. Tab
09. Accordion
10. Isotope
11. Prettyphoto
12. Slick_slider
13. Back to top 

 =============== */


(function ($) {

    'use strict'


    /*------------------------------------------------------------------------------*/
    /* Preloader
    /*------------------------------------------------------------------------------*/
    // makes sure the whole site is loaded
    $(window).on("load", function () {
        // will first fade out the loading animation
        $("#preloader").fadeOut();
        // will fade out the whole DIV that covers the website.
        $("#status").fadeOut(9000);
    })


    /*------------------------------------------------------------------------------*/
    /* header_search
    /*------------------------------------------------------------------------------*/

    $(document).ready(function () {

        $(".header_search").each(function () {

            var $this = $(this);

            $(".search_btn", $this).on("click", function (e) {
                e.preventDefault();
                e.stopPropagation();

                // Toggle search box
                $this.find(".header_search_content").toggleClass("on");

                var $btn = $(this);
                var $icon = $btn.find("i");

                if ($btn.hasClass("open")) {
                    $btn.removeClass("open").addClass("sclose");
                    $icon.removeClass("fa-xmark").addClass("fa-magnifying-glass");
                } else {
                    $btn.removeClass("sclose").addClass("open");
                    $icon.removeClass("fa-magnifying-glass").addClass("fa-xmark");
                }
            });

        });

        $(document).on("click", function (e) {
            if (!$(e.target).closest(".header_search").length) {
                $(".header_search_content").removeClass("on");
                $(".search_btn").removeClass("open").addClass("sclose");
                $(".search_btn i")
                    .removeClass("fa-xmark")
                    .addClass("fa-magnifying-glass");
            }
        });

    });

    $(function () {

        // appointment form animations
        $('.header_btn > a').on('click', function (event) {
            event.preventDefault();
            $('#appointment').fadeToggle();
        })
        $(this).mouseup(function (e) {


            var container = $("#appointment");

            if (!container.is(e.target) // if the target of the click isn't the container...
                && container.has(e.target).length === 0) // ... nor a descendant of the container
            {
                container.fadeOut();
            }
        });

    });



    /*------------------------------------------------------------------------------*/
    /* Datetimepicker
    /*------------------------------------------------------------------------------*/
    $(function () {
        $('#datetimepicker1').datetimepicker({
            daysOfWeekDisabled: [0, 6]
        });
    });



    /*------------------------------------------------------------------------------*/
    /* Fixed-header
    /*------------------------------------------------------------------------------*/

    $(window).scroll(function () {
        if (matchMedia('only screen and (min-width: 1200px)').matches) {
            if ($(window).scrollTop() >= 50) {

                $('.ttm-stickable-header').addClass('fixed-header');
            }
            else {

                $('.ttm-stickable-header').removeClass('fixed-header');
            }
        }
    });



    /*------------------------------------------------------------------------------*/
    /* Menu
    /*------------------------------------------------------------------------------*/

    var menu = {
        initialize: function () {
            this.Menuhover();
        },

        Menuhover: function () {
            var getNav = $("nav.main-menu"),
                getWindow = $(window).width(),
                getHeight = $(window).height(),
                getIn = getNav.find("ul.menu").data("in"),
                getOut = getNav.find("ul.menu").data("out");

            if (matchMedia('only screen and (max-width: 1200px)').matches) {

                // Enable click event
                $("nav.main-menu ul.menu").each(function () {

                    // Dropdown Fade Toggle
                    $("a.mega-menu-link", this).on('click', function (e) {
                        e.preventDefault();
                        var t = $(this);
                        t.toggleClass('active').next('ul').toggleClass('active');
                    });

                    // Megamenu style
                    $(".megamenu-fw", this).each(function () {
                        $(".col-menu", this).each(function () {
                            $(".title", this).off("click");
                            $(".title", this).on("click", function () {
                                $(this).closest(".col-menu").find(".content").stop().toggleClass('active');
                                $(this).closest(".col-menu").toggleClass("active");
                                return false;
                                e.preventDefault();

                            });

                        });
                    });
                });
            }
        },
    };


    $('.btn-show-menu-mobile').on('click', function (e) {
        $(this).toggleClass('is-active');
        $('.menu-mobile').toggleClass('show');
        return false;
        e.preventDefault();
    });

    // Initialize
    $(document).ready(function () {
        menu.initialize();

    });


    /*------------------------------------------------------------------------------*/
    /* Animation on scroll: Number rotator
    /*------------------------------------------------------------------------------*/

    $("[data-appear-animation]").each(function () {
        var self = $(this);
        var animation = self.data("appear-animation");
        var delay = (self.data("appear-animation-delay") ? self.data("appear-animation-delay") : 0);

        if ($(window).width() > 959) {
            self.html('0');
            self.waypoint(function (direction) {
                if (!self.hasClass('completed')) {
                    var from = self.data('from');
                    var to = self.data('to');
                    var interval = self.data('interval');
                    self.numinate({
                        format: '%counter%',
                        from: from,
                        to: to,
                        runningInterval: 2000,
                        stepUnit: interval,
                        onComplete: function (elem) {
                            self.addClass('completed');
                        }
                    });
                }
            }, { offset: '85%' });
        } else {
            if (animation == 'animateWidth') {
                self.css('width', self.data("width"));
            }
        }
    });



    /*------------------------------------------------------------------------------*/
    /* Skillbar
    /*------------------------------------------------------------------------------*/

    $('.ttm-progress-bar').each(function () {
        $(this).find('.progress-bar').width(0);
    });

    $('.ttm-progress-bar').each(function () {

        $(this).find('.progress-bar').animate({
            width: $(this).attr('data-percent')
        }, 2000);
    });


    // Part of the code responsible for loading percentages:

    $('.progress-bar-percent[data-percentage]').each(function () {

        var progress = $(this);
        var percentage = Math.ceil($(this).attr('data-percentage'));

        $({ countNum: 0 }).animate({ countNum: percentage }, {
            duration: 2000,
            easing: 'linear',
            step: function () {
                // What todo on every count
                var pct = '';
                if (percentage == 0) {
                    pct = Math.floor(this.countNum) + '%';
                } else {
                    pct = Math.floor(this.countNum + 1) + '%';
                }
                progress.text(pct);
            }
        });
    });

    /*------------------------------------------------------------------------------*/
    /* Tab
    /*------------------------------------------------------------------------------*/

    $(document).ready(function () {

        $('.content-tab').children('.content-inner').first().addClass('active');
        $('.ttm-tabs .tabs li').on('click', function (e) {
            if (!$(this).hasClass('active')) {
                var i = $(this).index();
                $('.ttm-tabs .tabs li.active').removeClass('active');
                $('.content-tab .active').hide().removeClass('active');
                $(this).addClass('active');
                $($('.content-tab').children('.content-inner')[i]).fadeIn(600).addClass('active');
                e.preventDefault();
            }
        });
    });


    /*------------------------------------------------------------------------------*/
    /* Accordion
    /*------------------------------------------------------------------------------*/

    /*https://www.antimath.info/jquery/quick-and-simple-jquery-accordion/*/
    $(".accordion").each(function () {

        var allPanels = $('.toggle').children(".toggle-content").hide();
        $('.toggle').children(".toggle-content").eq(2).slideDown("easeOutExpo");
        $('.toggle').children(".toggle-title").children("a").eq(2).addClass("active");

        $('.toggle').children(".toggle-title").children("a").click(function () {
            var current = $(this).parent().next(".toggle-content");
            $(".toggle-title > a").removeClass("active");
            $(this).addClass("active");
            allPanels.not(current).slideUp("easeInExpo");
            $(this).parent().next().slideDown("easeOutExpo");
            return false;
        });

    });


    /*------------------------------------------------------------------------------*/
    /* Isotope
    /*------------------------------------------------------------------------------*/

    $(function () {

        if ($().isotope) {
            var $container = $('.isotope-project');
            $container.imagesLoaded(function () {
                $container.isotope({
                    itemSelector: '.ttm-box-col-wrapper',
                    transitionDuration: '1s',
                    layoutMode: 'fitRows'
                });
            });

            $('.portfolio-filter li').on('click', function () {
                var selector = $(this).find("a").attr('data-filter');
                $('.portfolio-filter li').removeClass('active');
                $(this).addClass('active');
                $container.isotope({ filter: selector });
                return false;
            });
        };

    });



    /*------------------------------------------------------------------------------*/
    /* Prettyphoto
    /*------------------------------------------------------------------------------*/
    $(function () {

        // Normal link
        jQuery('a[href*=".jpg"], a[href*=".jpeg"], a[href*=".png"], a[href*=".gif"]').each(function () {
            if (jQuery(this).attr('target') != '_blank' && !jQuery(this).hasClass('prettyphoto') && !jQuery(this).hasClass('modula-lightbox')) {
                var attr = $(this).attr('data-gal');
                if (typeof attr !== typeof undefined && attr !== false && attr != 'prettyPhoto') {
                    jQuery(this).attr('data-rel', 'prettyPhoto');
                }
            }
        });

        jQuery('a[data-gal^="prettyPhoto"]').prettyPhoto();
        jQuery('a.ttm_prettyphoto').prettyPhoto();
        jQuery('a[data-gal^="prettyPhoto"]').prettyPhoto();
        jQuery("a[data-gal^='prettyPhoto']").prettyPhoto({ hook: 'data-gal' })

    });
    $(document).ready(function () {
        var e = '<div class="prt_floting_customsett">' +
            '<a href="https://support.preyantechnosys.com/" class="tmtheme_fbar_icons"><i class="fa fa-headphones"></i><span>Support</span></a>' +
            '<a href="https://preyantechnosys.com/" class="tmtheme_fbar_icons"><i class="themifyicon themifyicon ti-pencil"></i><span>Customization</span></a>' +
            '<a href="https://1.envato.market/j0D25" class="tmtheme_fbar_icons"><i class="themifyicon ti-shopping-cart"></i><span class="buy_link">Buy<span></span></span></a>' +
            '<div class="clearfix"></div>' +
            '</div>';

        $('body').append(e);
    });


    /*------------------------------------------------------------------------------*/
    /* Slick_slider
    /*------------------------------------------------------------------------------*/
    $(".slick_slider").slick({
        speed: 1000,
        infinite: true,
        arrows: false,
        dots: false,
        autoplay: false,
        centerMode: false,

        responsive: [{

            breakpoint: 1360,
            settings: {
                slidesToShow: 3,
                slidesToScroll: 3
            }
        },
        {

            breakpoint: 1024,
            settings: {
                slidesToShow: 3,
                slidesToScroll: 3
            }
        },
        {

            breakpoint: 680,
            settings: {
                slidesToShow: 2,
                slidesToScroll: 2
            }
        },
        {
            breakpoint: 575,
            settings: {
                slidesToShow: 1,
                slidesToScroll: 1
            }
        }]
    });




    jQuery(document).ready(function ($) {
        if (jQuery('body').hasClass('ttm-one-page-site')) {
            var sections = jQuery('.ttm-row'),
                nav = jQuery('.ttm-header-wrap, .menu'),
                nav_height = jQuery('#site-navigation').data('sticky-height') - 1;

            jQuery(window).on('scroll', function () {
                if (jQuery('body').scrollTop() < 5) {
                    nav.find('a').parent().removeClass('active');
                }
                var cur_pos = jQuery(this).scrollTop();
                sections.each(function () {
                    var top = jQuery(this).offset().top - (nav_height + 1),
                        bottom = top + jQuery(this).outerHeight();
                    if (cur_pos >= top && cur_pos <= bottom) {
                        if (typeof jQuery(this) != 'undefined' && typeof jQuery(this).attr('id') != 'undefined' && jQuery(this).attr('id') != '') {
                            var mainThis = jQuery(this);
                            nav.find('a').removeClass('active');
                            jQuery(this).addClass('active');
                            var arr = mainThis.attr('id');

                            // Applying active class
                            nav.find('a').parent().removeClass('active');
                            nav.find('a').each(function () {
                                var menuAttr = jQuery(this).attr('href').split('#')[1];
                                if (menuAttr == arr) {
                                    jQuery(this).parent().addClass('active');
                                }
                            })
                        }
                    }
                });
                //}
            });

            nav.find('a').on('click', function () {
                var $el = jQuery(this),
                    id = $el.attr('href');
                var arr = id.split('#')[1];
                jQuery('html, body').animate({
                    scrollTop: jQuery('#' + arr).offset().top - nav_height
                }, 500);
                return false;
            });

        }

    }); // END of  document.ready


    /*------------------------------------------------------------------------------*/
    /* Back to top
    /*------------------------------------------------------------------------------*/

    // ===== Scroll to Top ==== 
    jQuery('#totop').hide();

    jQuery(window).scroll(function () {
        "use strict";
        if (jQuery(this).scrollTop() >= 1000) {        // If page is scrolled more than 50px
            jQuery('#totop').fadeIn(200);    // Fade in the arrow
            jQuery('#totop').addClass('top-visible');
        } else {
            jQuery('#totop').fadeOut(200);   // Else fade out the arrow
            jQuery('#totop').removeClass('top-visible');
        }
    });

    // Scroll to Top Button
    jQuery('#totop').on("click", function () {
        jQuery('html, body').animate({
            scrollTop: 0
        }, 500);
        return false;
    });


    // Sticky Header Fix
    window.addEventListener("scroll", function () {
        let header = document.querySelector(".ttm-stickable-header");

        if (header) {
            if (window.scrollY > 100) {
                header.classList.add("fixed-header");
            } else {
                header.classList.remove("fixed-header");
            }
        }
    });


    // Revolution Slider Init
    jQuery(document).ready(function () {

        if (jQuery("#rev_slider").length) {

            jQuery("#rev_slider").show().revolution({
                sliderType: "standard",
                sliderLayout: "fullscreen",
                delay: 5000,

                navigation: {
                    arrows: { enable: true }
                },

                responsiveLevels: [1240, 1024, 778, 480],
                gridwidth: [1240, 1024, 778, 480],
                gridheight: [768, 600, 500, 400]
            });

        }

    });

})(jQuery);