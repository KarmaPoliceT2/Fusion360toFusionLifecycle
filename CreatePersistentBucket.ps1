#Author-Chris Gill
#Description-AU 2018 Demonstration of Sending data from F360 to Fusion Lifecycle & Forge

# This powershell script creates a bucket for the catalog to work against.

Write-Host "Running script to create a persistent Forge Bucket for storing translated catalog data"

# Setup Token Request
    # Get User Inputs
$ForgeClientId = Read-Host -Prompt 'Input your Forge Client ID: '
$ForgeClientSecret = Read-Host -Prompt 'Input your Forge Client Secret: '
    # Set fixed Inputs
$tokenURL = 'https://developer.api.autodesk.com/authentication/v1/authenticate'
$grantType = 'client_credentials'
$scopes = "bucket:create bucket:read data:write"
$headers = @{ 
    'Content-Type' = 'application/x-www-form-urlencoded' 
}
$body = @{ 
    client_id = $ForgeClientId
    client_secret = $ForgeClientSecret
    grant_type = $grantType
    scope = $scopes
}

# Login & get a token
Write-Host "Logging In..."
$LoginResponse = Invoke-RestMethod -Method Post -Uri $tokenURL -Headers $headers -Body $body

#setup Bucket Create
    # Get User Inputs
$bucketName = Read-Host -Prompt 'Input the bucket name you wish to create: '
    # Set fixed Inputs
$bucketURL = 'https://developer.api.autodesk.com/oss/v2/buckets'
$headers = New-Object "System.Collections.Generic.Dictionary[[String],[String]]"
$headers.Add("Content-Type", 'application/json' )
$headers.Add("Authorization", "$($LoginResponse.token_type) $($LoginResponse.access_token)")
$body = @{
   bucketKey = $bucketName
   policyKey = 'persistent'
}
$jsonBody = $body | ConvertTo-Json

#Create the bucket
Write-Host "Creating the bucket..."
$BucketCreateResponse = Invoke-RestMethod -Method Post -Uri $bucketURL -Headers $headers -Body $jsonBody

Write-Host $BucketCreateResponse
