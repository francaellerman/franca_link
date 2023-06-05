# franca_link
### About this repository
The folder franca_link is a Flask app folder (I forget the right name). In there is all of the logic of Quickly and the front-end. This was originally the only folder in this repository and what the setup.py is based on.
The folder franca_link also includes the folder my_logging for Quickly's logging which connects to my email and took me an insane amount of time to set up. Actually, a lot of Quickly uses this crazy logging system so you might want to get rid of the parts of Quickly that use it unless you are crazy like me :)
to_etc is a folder of what should go where you put configurations (on Linux it's usually under /etc/your_app hence etc).
data is what the folder where you put your data should look like.
### What you'll need
Some of the data files need to be sort of instantiated with functions that are in franca_link.
You'll also need to set up a daemon to sync the school calendar with Quickly (the function is in franca_link).
This repository just has the Flask app, not what you'll need to run the Flask app on your server. I did not include my files and scripts for UWSGI, daemons, and thesuch because that's going to be pretty particular to how you want to set up your server.
Also keep in mind that the school can change what the PDF schedules look like any year, so what worked on Quickly this year might not work next year.
I haven't really cleaned up any of this code and I mostly worked on Quickly this summer (so a year ago). There's a lot I've forgotten so if something doesn't work or doesn't make sense, it could be my bad. Let me know!
### What I ask of you
Similar to when Ben Borgers asked people not to call themselves "Blocks 2.0" or similar, I ask the same of your app's name (but you can reference it just like Quickly references Daily!). And while I've made Quickly's interface public, if you use it, make sure you make enough changes users don't think I made it (and graphic design is fun anyways!). However, the code behind the front-end can is all fair game as long as you're crediting Quickly for LHS with a link to this repository somewhere (ex. the about page).
### Miscellaneous
I actually made an app before Quickly called LHS 2023 Connections. Before our senior year, seniors were given these class lists during the summer that told us what class groups we would be in. By uploading this list, you could see who was in your classes next year. If LHS does this again and you want to bring LHS Connections back, let me know and I'll put it on GitHub!
