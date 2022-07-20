const {createApp} = Vue

new ClipboardJS('#copy_space .list-group-item-action')

var app = createApp({
    data() {
        return {
            started_uploading: false,
            cookie: false,
            name: '',
            connections: null,
            errors: null,
            loona: 'Loona'
        }
    },
    async created() {
        this.get_connections()
    },
    methods: {
        async upload() {
            this.started_uploading = await true
            const formData = await new FormData();
            const fileField = await document.querySelector('input[type="file"]');
            await formData.append('pdf', fileField.files[0]);
            //Cookie is put in browser with fetch's return
            await fetch('api', {
              method: 'POST',
              body: formData
            })
            await this.get_connections()
            if (await this.cookie) {
                this.errors = null
            }
            else if (!this.errors) {
                //This is to not override a connections error message
                this.errors = "There's been an error processing your PDF."
            }
        },
        async get_connections() {
            await fetch('api', {method: 'GET'}).then(async resp => {
                    if(await resp.ok){
                        this.errors = null
                        let j = await resp.json()
                        if (j == 'No ID'){
                            this.cookie = false
                        }
                        else {
                            this.cookie = true
                            this.name = j['name']
                            this.connections = j['class_list']
                        }
                    }
                    else{
                        this.errors = await "There's been an error retrieving your connections."
                    }
                })
        },
        async reset(event){
            await fetch('reset', {method: 'GET'})
            await window.location.reload()
        }
    },
    delimiters: ['[[',']]']
}).mount('body')

//WW3 schools
function get_cookie(cname) {
  let name = cname + "=";
  let decodedCookie = decodeURIComponent(document.cookie);
  let ca = decodedCookie.split(';');
  for(let i = 0; i <ca.length; i++) {
    let c = ca[i];
    while (c.charAt(0) == ' ') {
      c = c.substring(1);
    }
    if (c.indexOf(name) == 0) {
      return c.substring(name.length, c.length);
    }
  }
  return "";
}

function set_cookie(key, value) {
    document.cookie = key + "=" + value + "; expires=Fri, 31 Dec 9999 23:59:59 GMT; SameSite=Strict"
}
