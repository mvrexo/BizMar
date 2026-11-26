# Offline UAT authentication preflight tests. All values are synthetic.
import copy
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import uat_auth_preflight as pre
import uat_launch

def fixture():
 secrets=dict(SUPABASE_URL='https://'+'t'*20+'.supabase.co',SUPABASE_ANON_KEY='sb_publishable_'+'a'*40,
              OWNER_EMAIL='owner@uat.invalid',ADMIN_PASSWORD='b'*32,
              auth=dict(redirect_uri=pre.CALLBACK,cookie_secret='c'*40,client_id='123456789012-uatonly.apps.googleusercontent.com',
                        client_secret='SYNTHETIC_TEST_SECRET',server_metadata_url=pre.METADATA))
 approval=dict(environment='dedicated-uat',owner_attests_no_production_data_access=True,
               approved_supabase_url=secrets['SUPABASE_URL'],approved_google_client_id=secrets['auth']['client_id'],
               google_client_mode='dedicated-test',owner_approves_existing_google_client=False,
               owner_attests_separate_development_cookie_secret=True)
 return secrets,approval

class AuthConfigurationTests(unittest.TestCase):
 def test_valid_synthetic_configuration(self):
  self.assertEqual(pre.validate_configuration(*fixture())['status'],'passed')
 def test_missing_credentials(self):
  secrets,approval=fixture();secrets.pop('SUPABASE_ANON_KEY')
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_invalid_table_shape(self):
  for secrets,approval in (([],{}),({},[])):
   with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_production_like_endpoint_not_allowlisted(self):
  secrets,approval=fixture();secrets['SUPABASE_URL']='https://'+'p'*20+'.supabase.co'
  with self.assertRaisesRegex(pre.PreflightError,'explicitly approved'):pre.validate_configuration(secrets,approval)
 def test_owner_attestation_required(self):
  secrets,approval=fixture();approval['owner_attests_no_production_data_access']=False
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_missing_google_client(self):
  secrets,approval=fixture();del secrets['auth']['client_secret']
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_google_client_must_match_approval(self):
  secrets,approval=fixture();secrets['auth']['client_id']='999999999-other.apps.googleusercontent.com'
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_callback_must_match_guarded_origin(self):
  for url in ('http://127.0.0.1:8501/oauth2callback','http://localhost:8502/oauth2callback','http://localhost:8501/','http://localhost:8501/oauth2callback?code=synthetic'):
   secrets,approval=fixture();secrets['auth']['redirect_uri']=url
   with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_google_metadata_cannot_be_redirected(self):
  secrets,approval=fixture();secrets['auth']['server_metadata_url']='https://unapproved.invalid/discovery'
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_privileged_credentials_rejected(self):
  secrets,approval=fixture();secrets['SUPABASE_SERVICE_ROLE_KEY']='synthetic'
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_placeholders_fail_closed(self):
  secrets,approval=fixture();secrets['ADMIN_PASSWORD']='REPLACE_SEPARATE_DEVELOPMENT_ADMIN_PASSWORD'
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_error_messages_do_not_echo_values(self):
  secrets,approval=fixture();sentinel='sensitive-value-not-to-log';secrets['SUPABASE_URL']=sentinel
  try:pre.validate_configuration(secrets,approval)
  except pre.PreflightError as error:self.assertNotIn(sentinel,str(error))
  else:self.fail('Expected rejection')
 def test_no_network_or_server_during_validation(self):
  with patch.object(socket,'create_connection',side_effect=AssertionError('Network forbidden')),patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')),patch.object(uat_launch.runpy,'run_path',side_effect=AssertionError('Server forbidden')):
   self.assertEqual(pre.validate_configuration(*fixture())['status'],'passed')
 def test_check_only_wrapper_never_starts_streamlit(self):
  with patch.object(uat_launch,'preflight',return_value={'status':'passed'}),patch.object(uat_launch.runpy,'run_path',side_effect=AssertionError('Server forbidden')):
   self.assertEqual(uat_launch.main([]),0)
 def test_failed_preflight_cannot_delegate_to_launcher(self):
  with patch.object(uat_launch,'preflight',side_effect=pre.PreflightError('Synthetic missing configuration')),patch.object(uat_launch.runpy,'run_path',side_effect=AssertionError('Server forbidden')):
   self.assertEqual(uat_launch.main(['--launch']),1)
 def test_runtime_configuration_shape_keys(self):
  source=(ROOT/'uat_launch.py').read_text()
  self.assertIn("config.set_option('secrets.files',[str(root/'.streamlit/secrets.toml')])",source)
  self.assertIn("runpy.run_path(str(root.parent/'launch_dev.py'),run_name='__main__')",source)

 def test_approved_launch_delegates_only_to_original_guard_mock(self):
  with patch.object(uat_launch,'preflight',return_value={'status':'passed'}),patch('streamlit.config.set_option') as configure,patch('streamlit.config.on_config_parsed') as parsed,patch.object(uat_launch.runpy,'run_path',return_value={}) as delegate,patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')):
   self.assertEqual(uat_launch.main(['--launch']),0)
   delegate.assert_called_once_with(str(ROOT.parent/'launch_dev.py'),run_name='__main__')
   self.assertTrue(parsed.call_args.kwargs['force_connect'])
   configure.reset_mock();parsed.call_args.args[0]()
   self.assertIn(unittest.mock.call('secrets.files',[str(ROOT/'.streamlit/secrets.toml')]),configure.call_args_list)
   self.assertIn(unittest.mock.call('server.address','127.0.0.1'),configure.call_args_list)

class GoogleClientModeTests(unittest.TestCase):
 def shared(self):
  secrets,approval=fixture()
  approval.update(google_client_mode='owner-approved-existing',owner_approves_existing_google_client=True)
  return secrets,approval
 def test_dedicated_mode_is_distinct(self):
  result=pre.validate_configuration(*fixture())
  self.assertEqual(result['google_client_mode'],'dedicated-test')
  self.assertFalse(result['reduced_authentication_isolation']);self.assertIsNone(result['warning'])
 def test_owner_approved_existing_mode_discloses_shared_production_client(self):
  result=pre.validate_configuration(*self.shared())
  self.assertEqual(result['google_client_mode'],'owner-approved-existing')
  self.assertTrue(result['reduced_authentication_isolation']);self.assertIn('shared with production',result['warning'])
 def test_existing_client_without_explicit_approval_is_rejected(self):
  secrets,approval=self.shared();approval['owner_approves_existing_google_client']=False
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_unknown_or_missing_mode_rejected(self):
  for mode in (None,'existing','production','dedicated'):
   secrets,approval=fixture();approval['google_client_mode']=mode
   with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_dedicated_mode_cannot_hide_shared_client_approval(self):
  secrets,approval=fixture();approval['owner_approves_existing_google_client']=True
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_separate_cookie_attestation_required_both_modes(self):
  for factory in (fixture,self.shared):
   secrets,approval=factory();approval['owner_attests_separate_development_cookie_secret']=False
   with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_no_production_data_attestation_required_both_modes(self):
  for factory in (fixture,self.shared):
   secrets,approval=factory();approval['owner_attests_no_production_data_access']=False
   with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_exact_client_allowlist_required_both_modes(self):
  for factory in (fixture,self.shared):
   secrets,approval=factory();secrets['auth']['client_id']='999999999-unapproved.apps.googleusercontent.com'
   with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_callback_and_discovery_unchanged_both_modes(self):
  for factory in (fixture,self.shared):
   for key,value in (('redirect_uri','http://localhost:8502/oauth2callback'),('server_metadata_url','https://unapproved.invalid/discovery')):
    secrets,approval=factory();secrets['auth'][key]=value
    with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_supabase_and_privilege_restrictions_unchanged_both_modes(self):
  for factory in (fixture,self.shared):
   secrets,approval=factory();secrets['SUPABASE_URL']='https://'+'p'*20+'.supabase.co'
   with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
   secrets,approval=factory();secrets['SUPABASE_SERVICE_ROLE_KEY']='synthetic-forbidden'
   with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_legacy_ambiguous_approval_is_not_silently_accepted(self):
  secrets,approval=fixture();approval['owner_attests_no_production_access']=True
  with self.assertRaises(pre.PreflightError):pre.validate_configuration(secrets,approval)
 def test_mode_diagnostics_do_not_expose_credentials(self):
  for factory in (fixture,self.shared):
   secrets,approval=factory();result=json.dumps(pre.validate_configuration(secrets,approval))
   for value in (secrets['SUPABASE_ANON_KEY'],secrets['OWNER_EMAIL'],secrets['ADMIN_PASSWORD'],secrets['auth']['client_secret'],secrets['auth']['cookie_secret'],secrets['auth']['client_id']):
    self.assertNotIn(value,result)


class PrivatePathTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'NourSweet';self.root.mkdir()
  path=self.root/'uat_auth_preflight.py';path.write_bytes((ROOT/'uat_auth_preflight.py').read_bytes())
  spec=importlib.util.spec_from_file_location('synthetic_preflight',path);self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
 def tearDown(self):self.temp.cleanup()
 def test_missing_files_do_not_fall_back_or_create_files(self):
  with self.assertRaises(self.module.PreflightError):self.module.preflight()
  self.assertFalse((self.root/'.streamlit').exists())
 def test_wrong_source_directory_rejected(self):
  with self.assertRaisesRegex(self.module.PreflightError,'own isolated'):self.module.preflight(ROOT)
 def test_invalid_toml_redacted(self):
  private=self.root/'.streamlit';private.mkdir()
  (private/'secrets.toml').write_text('password = "SYNTHETIC_UNCLOSED')
  (private/'uat-approval.toml').write_text('environment="dedicated-uat"')
  original=self.root.parent/'original.sqlite3';original.write_bytes(b'synthetic original')
  database=self.root/'nour_sweets.sqlite3';database.write_bytes(b'synthetic dev')
  (self.root.parent/'isolation.json').write_text(json.dumps(dict(workspace=str(self.root),database=str(database),production_database=str(original),development_localappdata=str(self.root.parent/'localappdata'))))
  try:self.module.preflight()
  except self.module.PreflightError as error:self.assertNotIn('SYNTHETIC_UNCLOSED',str(error))
  else:self.fail('Expected parsing rejection')
 def test_private_templates_are_not_runtime_credentials(self):
  private=self.root/'.streamlit';private.mkdir()
  (private/'secrets.toml.example').write_text('placeholder')
  (private/'uat-approval.toml.example').write_text('placeholder')
  with self.assertRaises(self.module.PreflightError):self.module.preflight()

 def test_linked_private_directory_rejected_before_read(self):
  with patch.object(Path,'is_symlink',return_value=True):
   with self.assertRaisesRegex(self.module.PreflightError,'symbolic links'):self.module.preflight()
 def test_database_outside_development_tree_rejected(self):
  private=self.root/'.streamlit';private.mkdir()
  (private/'secrets.toml').write_text('placeholder = true')
  (private/'uat-approval.toml').write_text('placeholder = true')
  original=self.root.parent/'original.sqlite3';original.write_bytes(b'synthetic')
  (self.root.parent/'isolation.json').write_text(json.dumps(dict(workspace=str(self.root),database=str(original),production_database=str(original),development_localappdata=str(self.root.parent/'localappdata'))))
  with self.assertRaisesRegex(self.module.PreflightError,'SQLite path isolation'):self.module.preflight()

if __name__=='__main__':unittest.main()
