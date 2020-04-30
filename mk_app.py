#!/usr/bin/python3

#imports
import re, getopt, sys, yaml, json, requests, configparser
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Authenticate (vROps local user - consider updating script to allow for IDM)
def Authenticate():
	#Read Config parameters
	config = configparser.ConfigParser()
	config.read('config.ini')

	#Your vROps environment parameters
	usrName = config['vrops user']['usrName']
	usrPass = config['vrops user']['usrPass']
	srvName = config['vrops server']['srvName']

	global baseURL
	baseURL = "https://" + srvName

	tokenURL = baseURL + "/suite-api/api/auth/token/acquire"
	authJSON = {"username": usrName,"authSource": "Local","password": usrPass,"others": [],"otherAttributes": {}}
	authHeaders = {"Content-Type":"application/json","Accept":"application/json"}
	authResponse = requests.post(tokenURL,data=json.dumps(authJSON),headers=authHeaders,verify=False)
	if (authResponse.status_code != 200):
		print('probably invalid credentials')
		print('Returned Status Code: ' + authResponse.status_code)
		sys.exit
	else:
		authToken = "vRealizeOpsToken " + authResponse.json()['token']
		return authToken

# Obtain the Container ID
def ObtainContainerId(token):
	vropsURL = baseURL + "/suite-api/api/adapters?adapterKindKey=Container"
	Headers = {"Content-Type":"application/json","Authorization":token,"Accept":"application/json"}
	response = requests.get(vropsURL,headers=Headers,verify=False)
	if (response.status_code == 200):
		return(response.json()['adapterInstancesInfoDto'][0]['id'])
	else:
		print("We had a problem in the process to Obtain a Container ID")
		print(response.text)
		sys.exit(2)

def StartCollecting(token, ObjId):
		vropsURL = baseURL + "/suite-api/api/resources/"+ObjId+"/monitoringstate/start"
		Headers = {"Content-Type":"application/json","Authorization":token,"Accept":"application/json"}
		response = requests.put(vropsURL,headers=Headers,verify=False)

def CreateApplicationTier(token,ApplicationId,ContainerId,TierName):
		vropsURL = baseURL + "/suite-api/api/resources/adapters/"+ContainerId
		Headers = {"Content-Type":"application/json","Authorization":token,"Accept":"application/json"}
		tierData = {
			"creationTime": None,
			"resourceKey": {
				"name": TierName,
				"adapterKindKey": "Container",
				"resourceKindKey": "Tier",
				"resourceIdentifiers": [ {
					"identifierType": {
						"name": "BS_Tier Name",
						"dataType": "STRING",
						"isPartOfUniqueness": True
					},
					"value": ApplicationId+"_"+TierName
				} ]
			},
			"resourceStatusStates": [],
			"resourceHealth": None,
			"resourceHealthValue": None,
			"dtEnabled": True,
			"monitoringInterval": 5,
			"badges": [],
			"relatedResources": [],
			"identifier": None
		}
		response = requests.post(vropsURL,headers=Headers,data=json.dumps(tierData),verify=False)
		return(response.json()['identifier'])

def CreateRelationship(token,AppObjId,TierObjId):
		vropsURL = baseURL + "/suite-api/api/resources/"+TierObjId+"/relationships/parents"
		relData = {
			"uuids": [ AppObjId ]
		}
		Headers = {"Content-Type":"application/json","Authorization":token,"Accept":"application/json"}
		response = requests.post(vropsURL,headers=Headers,data=json.dumps(relData),verify=False)

def AddObjectToTier(token,TierObjId,ResId):
		vropsURL = baseURL + "/suite-api/api/resources/"+TierObjId+"/relationships/children"
		relData = {
			"uuids": [ ResId ]
		}
		Headers = {"Content-Type":"application/json","Authorization":token,"Accept":"application/json"}
		response = requests.post(vropsURL,headers=Headers,data=json.dumps(relData),verify=False)

def CreateApplication(token,ContainerId):
	with open("SingleApp.yaml") as f:
		appData = (json.dumps(yaml.load(f)))
		json_data = json.loads(appData)
	for app in json_data:
		appName = app['name']
		containerData = {
			"creationTime": None,
			"resourceKey": {
				"name": appName,
				"adapterKindKey": "Container",
				"resourceKindKey": "BusinessService",
				"resouceIdentifiers": []
			},
			"resourceStatusStates": [],
 			"resourceHealth": None,
 			"resourceHealthValue": None,
			"dtEnabled": True,
			"monitoringInterval": 5,
			"badges": [],
			"relatedResources": [],
			"identifier": None
		}
		vropsURL = baseURL + "/suite-api/api/resources/adapters/"+ContainerId
		Headers = {"Content-Type":"application/json","Authorization":token,"Accept":"application/json"}
		response = requests.post(vropsURL,headers=Headers,data=json.dumps(containerData),verify=False)
		print(response.status_code)
		if (response.status_code >= 200 or response.status_code <= 299):
			applicationObjectId = response.json()['identifier']
			StartCollecting(token,applicationObjectId)
			for x in range(app['no_of_tiers']):
				TierName = app['tiers']['results'][x]['name']
				TierObjectId = CreateApplicationTier(token,applicationObjectId,ContainerId,TierName)
				StartCollecting(token,TierObjectId)
				CreateRelationship(token,applicationObjectId,TierObjectId)
				print("Tier Created: " + TierName)
				
				if (app['tiers']['results'][x]['group_membership_criteria'][0]['membership_type'] == 'SearchMembershipCriteria'):
					Filter = app['tiers']['results'][x]['group_membership_criteria'][0]['search_membership_criteria']['filter']
					## Getting VM names when they're between single quote marks
					vmList = re.findall(r'\'(.*?)(?<!\\)\'', Filter)
					print(vmList)
					for vm in vmList:
						vmID = SearchName(token,vm)
						AddObjectToTier(token,TierObjectId,vmID)

# Search vROps database for the VM Name
def SearchName(token, vm_name):
	Headers = {"Content-Type":"application/json","Authorization":token,"Accept":"application/json"}
	vropsURL = baseURL+"/suite-api/api/adapterkinds/VMWARE/resourcekinds/virtualmachine/resources?identifiers[VMEntityName]="+vm_name
	response = requests.get(vropsURL,headers=Headers,verify=False)
	if response.json()['pageInfo']['totalCount'] == 0:
		return ('Searched term not found')
	else:
### The commented section is used when the vm-name can return multiple search results
#		for x in range(int(response.json()['pageInfo']['totalCount'])):
#			msg = response.json()['resourceList'][x]['resourceKey']['name']+": "
#			msg += response.json()['resourceList'][x]['identifier']+" "
#			msg += response.json()['resourceList'][x]['resourceKey']['resourceIdentifiers'][2]['value']
#			print(msg)
#		return ('Searched term was successful')
### For this application, we are assuming only one vm matches on the name search
		vmID = response.json()['resourceList'][0]['identifier']
	return(vmID)

def Logout(token):
	releaseURL = baseURL + "/suite-api/api/auth/token/release"
	authHeaders = {"Content-Type":"application/json","Authorization":token,"Accept":"application/json"}
	authResponse = requests.post(releaseURL,headers=authHeaders,verify=False)

def main():
	authToken = Authenticate()
	ContainerId = ObtainContainerId(authToken)
	CreateApplication(authToken,ContainerId)

	Logout(authToken)

# Script Starts Here
if __name__ == "__main__":
   main()
