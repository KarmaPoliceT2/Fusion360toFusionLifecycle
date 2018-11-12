#Author-Chris Gill
#Description-AU 2018 Demonstration of Sending data from F360 to Fusion Lifecycle & Forge

import adsk.core, adsk.fusion, adsk.cam, traceback, json, http.client, tempfile, base64, requests, collections

############################## EDIT THESE VARIABLES FOR YOUR USAGE #################################

flcTenantName = 'TENANT_NAME' 
flcTenantURL = flcTenantName + '.autodeskplm360.net'
flcUserID = "FLC_USER_ID"
flcUserPassword = "FLC_USER_PASSWORD"
forgeClientID = "FORGE_CLIENT_ID"
forgeClientSecret = "FORGE_CLIENT_SECRET"
forgeBucketKey = "FORGE_OSS_BUCKET_NAME"


############################## DO NOT EDIT BELOW HERE ##############################################
app = None
ui  = None
handlers = []

# Fucntion to login to FLC to get a token for all subsequent requests
def flcLogin():
    body = {
        "userID": flcUserID,
        "password": flcUserPassword
    }
    h = http.client.HTTPSConnection(flcTenantURL)
    headers = {
        'User-Agent': 'Fusion360',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    h.request('POST', '/rest/auth/1/login', json.dumps(body), headers)
    res = h.getresponse()
    return res.read()

# Function to get the FLC data we need in advance to populate the drop downs
def flcGetData(token):
    h = http.client.HTTPSConnection(flcTenantURL)
    headers = {
        "Cookie": "customer=" + flcTenantName + ";JSESSIONID=" + token,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    body = ""
    
    # Get the Supplier Companies Pick List    
    h.request('GET', '/api/rest/v1/setups/picklists/CUSTOM_LOOKUP_SUPPLIER_COMPANIES', body, headers)
    sRes = h.getresponse()
    suppliers = json.loads(sRes.read().decode('utf-8'))
    
    # Get the Part Categories Pick List
    h.request('GET', '/api/rest/v1/setups/picklists/CUSTOM_LOOKUP_PART_CATEGORIES', body, headers)
    cRes = h.getresponse()
    categories = json.loads(cRes.read().decode('utf-8'))
    
    # Get the list of Part Numbers
    h.request('GET', '/api/rest/v1/workspaces/65/items?size=20', body, headers)
    pRes = h.getresponse()
    partNumbers = json.loads(pRes.read().decode('utf-8'))
    
    return suppliers, categories, partNumbers

# Function to login to Forge to get a token for all subsequent requests    
def forgeLogin():
    base_url = 'https://developer.api.autodesk.com'    
    url_authenticate = base_url + '/authentication/v1/authenticate'
    
    data = {
        'client_id': forgeClientID,
        'client_secret': forgeClientSecret,
        'grant_type': 'client_credentials',
        'scope': 'bucket:read data:write data:read viewables:read'
    }
    
    r = requests.post(url_authenticate, data=data)
    return r.json()

def forgeTranslate(urn, token):
    translate_url = 'https://developer.api.autodesk.com/modelderivative/v2/designdata/job'
    headers = { 
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    }
    data = '{"input":{"urn":"'+urn.decode('utf-8')+'"},"output":{"destination":{"region":"us"},"formats":[{"type":"svf","views":["2d","3d"]}]}}'
    r = requests.post(translate_url, headers=headers, data=data)
    print(r.status_code)
    print(r.json)

def createOrUpdateFLCAttachment(dmsId, resourceName):
    tmpDir = tempfile.gettempdir()    
    fileName = resourceName+'.f3d'
    #Get all attachments of this dmsId
    checkUrl = 'https://'+flcTenantURL+'/api/rest/v1/workspaces/65/items/'+dmsId+'/attachments'    
    headers = {
        "Cookie": "customer=" + flcTenantName + ";JSESSIONID=" + flcToken
    }
    r = requests.get(checkUrl, headers=headers)
    attachments = r.json()
    found = False
    #Check if we got a list of attachments back    
    if attachments['list'] is not None:
        #Check if we have a matching fileName and         
        for file in attachments['list']['data']:
                #If we have a matching fileName retrieve its info & check it out
                if file['file']['fileName'] == fileName:
                    found = True       
                    existingFile = file['file']
                    checkoutUrl = checkUrl+'/'+str(existingFile['fileID'])+'/checkouts'
                    r = requests.post(checkoutUrl, headers=headers)
                    req_json = {}
                    req_json['fileName'] = existingFile['fileName']
                    req_json['resourceName'] = existingFile['resourceName']
                    req_json['description'] = existingFile['description']
                    req_json['fileVersion'] = str(existingFile['fileVersion'])
                    payload = collections.OrderedDict()
                    payload['json'] = (None, json.dumps(req_json), 'application/json')
                    payload['file'] = (None, open(tmpDir+'/'+fileName, 'rb'), 'application/octet-stream')
                    checkInHeaders = {
                        'Cookie': 'customer=' + flcTenantName + ';JSESSIONID=' + flcToken
                    }
                    checkinUrl = checkUrl+'/'+str(existingFile['fileID'])+'/checkins'                
                    requests.post(checkinUrl, files=payload, headers=checkInHeaders)
    # If we don't then create it new
    if not found:
        req_json = {}
        req_json['fileName'] = fileName
        req_json['resourceName'] = resourceName
        req_json['description'] = 'Created in Fusion 360'
        payload = collections.OrderedDict()
        payload['json'] = (None, json.dumps(req_json), 'application/json')
        payload['file'] = (None, open(tmpDir+'/'+fileName, 'rb'), 'application/octet-stream')
        headers = {
            "Cookie": "customer=" + flcTenantName + ";JSESSIONID=" + flcToken,
        }
        requests.post(checkUrl, files=payload, headers=headers)

# Event handler that executes the resulting operations after gathering inputs
class MyCommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            # Setup some info about the model, our capture values, and an export manager to give us an F3D
            design = app.activeProduct
            eventArgs = adsk.core.CommandEventArgs.cast(args)
            inputs = eventArgs.command.commandInputs
            exportMgr = design.exportManager
            tmpDir = tempfile.gettempdir()

            # Login to Forge
            forgeAuth = forgeLogin()
            forgeToken = forgeAuth["access_token"]

            # Export the Model as an F3D
            fusionArchiveOptions = exportMgr.createFusionArchiveExportOptions(tmpDir + '/' + inputs.itemById('partNumberInput').selectedItem.name + '.f3d')
            res = exportMgr.execute(fusionArchiveOptions)
            
            # If we generated an F3D file, upload it to Forge
            if res:
                upload_url = 'https://developer.api.autodesk.com/oss/v2/buckets/' + forgeBucketKey + '/objects/' + inputs.itemById('partNumberInput').selectedItem.name + '.f3d'
                headers = { 
                    'Authorization': 'Bearer ' + forgeToken,
                    'Content-Type': 'application/octet-stream'
                }
                with open(tmpDir + '/' + inputs.itemById('partNumberInput').selectedItem.name + '.f3d', 'rb') as f:
                    r = requests.put(upload_url, headers=headers, data=f)
                    uRes = r.json()
                if uRes:
                    urn = base64.urlsafe_b64encode(uRes['objectId'].encode('utf-8'))
                    forgeTranslate(urn.rstrip(b'='), forgeToken) #Translation will run in background, no checking built in for when it finishes at this time
                    # Update Fusion Lifecycle with the gathered data
                    selectedDmsId = inputs.itemById('flcDmsId').text
                    for part in partNums['list']['item']:
                        if part['details']['dmsID'] == int(selectedDmsId):
                            keys = ['PART_NUMBER', 'PART_NAME', 'PART_DESCRIPTION', 'PRODUCT_SUPPLIERS', 'PART_CATEGORY', 'BUCKETKEY', 'OBJECTID', 'OBJECTKEY', 'SHA1', 'SIZE', 'LOCATION', 'URN']
                            vals = [inputs.itemById("partNumberInput").selectedItem.name,
                                    inputs.itemById("partNameInput").text,
                                    inputs.itemById("partDescriptionInput").text,
                                    str(int(inputs.itemById("productSuppliersInput").selectedItem.index)+1),
                                    str(int(inputs.itemById("partCategoryInput").selectedItem.index)+2),
                                    uRes["bucketKey"],
                                    uRes["objectId"],
                                    uRes["objectKey"],
                                    uRes["sha1"],
                                    uRes["size"],
                                    uRes["location"],
                                    urn.decode("utf-8")
                                    ]
                            combine = dict(zip(keys,vals))
                            expand = [{"value": v, "key": k} for k, v in combine.items()]
                            req_json = {}
                            req_json["versionID"] = part["details"]["versionID"]
                            req_json["metaFields"] = {"entry": expand}
                            formatted_json = json.dumps(req_json)
                    if formatted_json:
                        update_url = 'https://'+flcTenantURL+'/api/rest/v1/workspaces/65/items/'+selectedDmsId
                        headers = {
                            "Cookie": "customer=" + flcTenantName + ";JSESSIONID=" + flcToken,
                            "Content-Type": "application/json",
                            "Accept": "application/json"
                        }
                        r = requests.put(update_url, headers=headers, data=formatted_json)
                        if 204 == r.status_code:
                            #Upload the F3D file to FLC as an attachment
                            createOrUpdateFLCAttachment(selectedDmsId, inputs.itemById('partNumberInput').selectedItem.name)
                            ui.messageBox('Successfully Saved')
            # When the command is done, terminate the script
            # This will release all globals which will remove all event handlers
            adsk.terminate()
        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# Event handler that reacts to any changes the user makes to any of the command inputs.
class MyCommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            if args.input.id == 'partNumberInput':
                partNumList = args.input                
                selItem = partNumList.selectedItem
                index = selItem.index
                
                flcDmsId = args.firingEvent.sender.commandInputs.itemById('flcDmsId')
                newText = str(partNums['list']['item'][index]['id'])
                flcDmsId.formattedText = newText
          
        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# Event handler that reacts to when the command is destroyed. This terminates the script.            
class MyCommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            # When the command is done, terminate the script
            # This will release all globals which will remove all event handlers
            adsk.terminate()
        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# Event handler that reacts when the command definition is executed which results in the command being created and this event being fired.
class MyCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            # Get the command that was created.
            cmd = adsk.core.Command.cast(args.command)
            
            # Connect to the command executed event.        
            onExecute = MyCommandExecuteHandler()
            cmd.execute.add(onExecute)
            handlers.append(onExecute)
            
            # Connect to the command destroyed event.
            onDestroy = MyCommandDestroyHandler()
            cmd.destroy.add(onDestroy)
            handlers.append(onDestroy)

            # Connect to the input changed event.           
            onInputChanged = MyCommandInputChangedHandler()
            cmd.inputChanged.add(onInputChanged)
            handlers.append(onInputChanged)    

            # Get the CommandInputs collection associated with the command.
            inputs = cmd.commandInputs

            #Get the setup data from FLC
            global suppliers, categories, partNums
            suppliers, categories, partNums = flcGetData(flcToken)

            # Part Number Input: Dropdown, Single Select
            partNumberInput = inputs.addDropDownCommandInput('partNumberInput', 'Part Number', adsk.core.DropDownStyles.TextListDropDownStyle)
            partNumberInputItems = partNumberInput.listItems
            for part in partNums['list']['item']:
                partNumberInputItems.add(part['description'], False)

            # Part Name Input: Editable TextBox
            inputs.addTextBoxCommandInput('partNameInput', 'Part Name', '', 1, False)
            
            # Part Description Input: Editable TextBox
            inputs.addTextBoxCommandInput('partDescriptionInput', 'Part Description', '', 1, False)

            # Part Category Input: Dropdown, Single Select
            partCategoryInput = inputs.addDropDownCommandInput('partCategoryInput', 'Part Category', adsk.core.DropDownStyles.TextListDropDownStyle)
            partCategoryInputItems = partCategoryInput.listItems
            for category in categories['picklist']['values']:
                partCategoryInputItems.add(category['label'], False)

            # Product Suppliers Input: Dropdown, Multi Select
            productSuppliersInput = inputs.addDropDownCommandInput('productSuppliersInput', 'Product Suppliers', adsk.core.DropDownStyles.TextListDropDownStyle)
            productSuppliersInputItems = productSuppliersInput.listItems
            for supplier in suppliers['picklist']['values']:
                productSuppliersInputItems.add(supplier['label'], False)    
            #productSuppliersInputItems.add('Item 1', False, 'resources/One')
            
            # FLC dmsId Input: Non-Editable TextBox
            inputs.addTextBoxCommandInput('flcDmsId', 'FLC dmsId', 'This is an example of a read-only text box.', 1, True)

        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def run(context):
    ui = None
    try:
        global app, ui, flcToken
        app = adsk.core.Application.get()
        ui  = app.userInterface
        
        #Login to FLC to get sessionid
        data = flcLogin()
        dataObject = json.loads(data.decode('utf-8'))
        flcToken = dataObject["sessionid"]
             
        # Get the existing command definition or create it if it doesn't already exist
        cmdDef = ui.commandDefinitions.itemById('f360toflc')
        if not cmdDef:
            cmdDef = ui.commandDefinitions.addButtonDefinition('f360toflc', 'Fusion 360 to Fusion Lifecycle & Forge', 'Sends design to FLC and Forge for use in the web catalog')
            
        # Connect to the command created event.
        onCommandCreated = MyCommandCreatedHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        handlers.append(onCommandCreated)
        
        # Execute the command definition
        cmdDef.execute()
        
        # Prevent this module from being terminated whent eh script returns, because we are waiting for event handlers to fire.
        adsk.autoTerminate(False)
        
    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
