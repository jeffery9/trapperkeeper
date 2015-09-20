/**
 * Initiate global websocket object.
 * @todo: Add user cookie for authentication.
 */
var host = location.origin.replace(/^http/, 'ws')
var ws = new WebSocket(host +"/message_wall" );

(function($){
  $.extend({
    playSound: function(){
      return $("<embed src='"+arguments[0]+".mp3' hidden='true' autostart='true' loop='false' class='playSound'>" + "<audio autoplay='autoplay' style='display:none;' controls='controls'><source src='"+arguments[0]+".mp3' /><source src='"+arguments[0]+".ogg' /></audio>").appendTo('body');
    }
  });
})(jQuery);

$(document).ready(function() {
    if (!window.console) window.console = {};
    if (!window.console.log) window.console.log = function() {};

    // Websocket callbacks:
    ws.onopen = function() {
        console.log("Connected...");
    };
    ws.onmessage = function (event) {
        data = JSON.parse(event.data);
        if (data.severity == "warning" || data.severity == "critical") {
            setTimeout($.playSound('../static/mp3/msg'), 650);
        }
        console.log("New Message", data);
        $('#table').load(document.URL + '# .table');
    };
    ws.onclose = function() {
        // @todo: Implement reconnect.
        console.log("Closed!");
        location.reload();
    };
});
