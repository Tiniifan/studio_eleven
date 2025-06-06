class Template:
    def __init__(self, name, modes, atr, mtr, outline_mesh_data, cmb1, cmb2):
        self.name = name
        self.modes = modes
        self.atr = atr
        self.mtr = mtr
        self.outline_mesh_data = outline_mesh_data
        self.cmb1 = cmb1
        self.cmb2 = cmb2
        
    def __str__(self):
        return self.name
        
    def __repr__(self):
        return self.name        

templates = [
        Template(
            "Inazuma Eleven Go",
            {
                "Object (Transparent)": ["759FE5F3", 1],
                "Map": ["F1697E54", 3],
            },
            "41545243303000000C000000230200000340C0FF01000000D51515157F5D5557FFFFFFF5000000000000000000000000",
            "4D5452433030000018004C00000000004C004C000000000021070000350000F001501301801C0340037E04800B5013F043F055F06760793FDF8003808E8000175003F023F0B7F0C98050DB004C5554433030000000001000000000000140000001E9886B3F000080F003FFF013F027F037F04BF05BF06FF07FF093FFF0A3F0B7F0C7F0DBF0EBF0FFF10FF123FFF133F147F157F16BF17BF18FF19FF1B3E0F1C3F1D7F1E73FDAE26A3E8010034EDF6A3EC4D46A003E61C36A3E4BAB6A003EA98C6A3EA0676A003E573C6A3EF30A6A003E9AD3693E739669003EA353693E500B69003EA1BD683EBB6A68003EC412683EE2B567003E3B54673EF6ED66003E3783663E261466003EE8A0653EA22965003E7CAE643E9B2F64003E25AD633E402763003E119E623EC01162003E7282613E4CF060003E755B603E14C45F003E4D2A5F3E478E5E003E27F05D3E14505D003E35AE5C3EAD0A5C003EA5655B3E41BF5A003EA8175A3EFF6E59003E6DC5583E181B58003E2570573EBBC456003EFF18563E176D55003E2BC1543E5E1554003ED869533EBFBE52003E3814523E696A51003E78C1503E8C1950003ECB724F3E59CD4E003E5E294E3EFF864D003E62E64C3EAE474C003E07AB4B3E95104B003E7D784A3EE5E249003EF34F493ECDBF48003E9932483E7EA847003EA021473E269E46003E361E463EF6A145003E8C29453E1EB544003ED244443ECDD843003E3771433E340E43003EEBAF423E825642003E1E02423EE7B241003E0169413E922441003EC2E5403EB5AC40003E9179403E7D4C40003E9F25403E1C0540003E1BEB3F3EC1D73F003E35CB3F3E9CC53F003E1DC73F3EDDCF3F003E03E03F3EB4F73F003E1617403E4F3E40003E866D403EE1A440003E84E4403E972C41003E3F7D413EA2D641003EE638423E32A442003EAA18433E769643003EBB1D443E9FAE44003E4849453EDCED45003E819C463E5D5547003E9618483E51E648003EB6BE493EEAA14A003E54B95C3E289EAD003E177F083F5D9D3E013FB8B8A33D0000F001FFF013F025F037F049F05BF06DF07FF091FFF0A3F0B5F0C7F0D9F0EBF0FDF10FF121FFF133F145F157F169F17BF18DF19FF1B1F0F1C3F1D5F1E751F963B700A00028B800188BB800B000C0B80010F5B800240014B900242DB900900045B900645DB9009C0074B900A085B900A60090B9005E9BB900CC00A5B900EEAFB900C400B9B9004EC3B9008A00CCB9007ED5B9002200DEB9007CE6B9008C00EEB9004CF6B900C200FDB9007602BA00E50005BA002F09BA0051000CBA004E0FBA00260012BA00D714BA00610017BA00C719BA0006001CBA00201EBA00130020BA00DF21BA00880023BA000825BA00640026BA009927BA00A90028BA009229BA0055082ABA00F300036A2BBA2A00BC0003E80007EC000BCDAA000F860013190017870023CFAA002BF10033EC003BC1004372A0004BFB00535F22BA009DA80063B4006BA70073721ABA00001818BA009815BA2000F200932610BA0034000DBA001B0ABA00DE0006BA007A03BA00E000FFB90080F8B900D400F0B900DCE8B9009800E0B9000AD8B9002C00CFB90006C6B9009200BCB900D2B2B900C804A8B9006E9E011B93B90000DE88B900407BB91000346401434CB900500034B900781BB9000C0002B90008D0B800D0009AB800C048B8002000B3B70080C0360000000C3800308138008800BD380010FB3800E4001C3900DC3C39006C005D39008C7E3900260090390050A13900C600B2390088C439009804D63900F0E80007FB39000045073A00E4103A0000A91A3A0094243A0000A52E3A00DC383A000039433A00BB4D3A000065583A0034633A0050BB903CF805FD3D000CC0463E1879583E0030AE333E00000000000000000000",
            [ 0.0249999985, 5.0, 1, 1.0, 1.0, 1.0, 1.0, 1, 0.0, 1.0, 1.0, 1.0, 1.0, 100.0, 60.0, 96000.0, 0.5, 0.0, 1, 1, 0.0025, 0.5, 0.4, 10.0, 60.0, 0.0, 0.0, 1 ],
            [ 1, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 255, 255, 255, 255, 0, 0, 0, 0 ],
            [ 3, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 3, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 255, 255, 255, 255, 0, 0, 0, 0 ],
        ),
        Template(
            "Inazuma Eleven CS/Galaxy", 
            {
                "Object (Transparent)": ["759FE5F3", 1],
                "Map": ["F1697E54", 3],
            },
            "41545243303100000C000000E3010000054080FF0000C0C13C80BF0137F72F406005FFFFF0FFFF56",
            "4D545243303000001800000000000000000000000000000041070000350000F001501301801C0340037E04800B5013F043F055F0673079F819FEFE3E5003B08B803F5003F0F023F0B5F0C770D9E8891DA70000004C555443",
            [ 0.0249999985, 5.0, 1, 1.0, 1.0, 1.0, 1.0, 1, 0.0, 1.0, 1.0, 1.0, 1.0, 100.0, 60.0, 96000.0, 0.5, 0.0, 1, 1, 0.0025, 0.5, 0.4, 10.0, 60.0, 0.0, 0.0, 1 ],
            [ 1, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 255, 255, 255, 255, 0, 0, 0, 0 ],
            [ 3, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 3, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 255, 255, 255, 255, 0, 0, 0, 0 ]
        ),
        Template(
            "Yo-Kai Watch", 
            {
                "Object (Transparent)": ["E093029A", 1],
                "Map": ["F1697E54", 3],
            },
            "41545243303100000C000000E3010000054080FF0000C0C13C80BF0137F72F406005FFFFF0FFFF56",
            "4D5452433030000018006000000000003004240C00000000410700001E010000A001900F101B500302AF002703002B044007500F500BF043E7F004F016107C803F7003F038109E00B2A0203EE9F0F03DF01003F02FF06CD07EF016E1980000004C555443303000000000100000000000044000007F0000803FC4FC7F3FF2F27F3F5BE27F3FD1CA7F3F24AC7F3F28867F3FAC587F3F83237F3F7EE67E3F6EA17E3F26547E3F76FE7D3F30A07D3F26397D3F29C97C3F0A507C3F9CCD7B3FAF417B3F15AC7A3F9F0C7A3F2063793F68AF783F49F1773F9428773F1C55763FB176753F258D743F4A98733FF097723FEA8B713F0974703F7F1F506F3FFC1F6E3F73E36C3F559A6B3F73446A3FA0E1683FAC71673F68F4653FA769643F3BD1623FF32A613FA3765F3F1BB45D3F2DE35B3FAA035A3F6415583F2C18563FD50B543F2FF0513F0CC54F3F3D8A4D3F943F4B3FC4EF483FF1C6463F1E7E443F6F16423F08913F3F0DEF3C3FA1313A3FEA59373F0A69343F2760313F7F63402E3FE40A2B3FCCC0273F4063243F64F3203F5D721D3F4DE1193F5941163FA693123F56D90E3F8E130B3F7343073F276A033FA011FF3E2141F73E1A65EF3ED47FE73E9593DF3EA7A2D73E51AFCF3EDCBBC73E8DCABF3EB1DDB73E8DF7AF3E671AA83E8B48A03E4084983ECCCF903E792D893E8F9F813EA750743E2494653E4F180E573E27C3483ED7B73A3EB5F02C3E57721F3E4B41123E1C62053EC2B2F13D4F57D93DF8BAC13DEAE6AA3D3EE4943D1E787F3D10EF563D7E3F303DBB7B0B3DF96BD13CF900903C29B6253CDBF5503BFF00FF00FF00FF00A7007F4FB800201DB900B884B90050BCB90068F5B900F017BA00F035BA00A454BA001474BA00208ABA00909ABA0060ABBA008CBCBA0014CEBA00FADFBA003EF2BA006E02BB00ED0BBB009A15BB00761FBB007F29BB00B833BB001F3EBB00B548BB007853BB006B5EBB008C69BB00DB74BB002D80BB000386BB80F08BBB00F591BB80117F98BB80449EBB008FA4BB00F1AABB8069B1BB00FAB7BB00A2BEBB8060C5BB0036CCBB0024D3BB0028DABB0044E1BB0077E8BB80C1EFBB0023F7BB009CFEBBC01503BC80E906BCC0C80ABCC0B30EBC40AA12BC00F413BCC0340ABCC03412BCC0EB19BCC05921BCC07E28BC005B2FBCC0ED35BC00383CBCC03842BC00F147BCC05F7F4DBC008652BC006357BC00F75BBCC04160BC004464BC00FD67BCC06C6BBC00946EBC007271BCC00674BC005376BCC05578BCE00F7ABCE0807BBCC0A87CBCE0877DBCC01D7EBCC06A7EBCA06E7EBCE0297EBC809B7DBC80C47CBCC0A47BBC803B7ABC608978BC808E76BC604A74BC40BD71BC70E76EBC30C86BBCC06068BC10AF4D64BC00B560BC20725CBCE0E557BCC01053BCF0F24DBCB08B48BC98DB42BCB8E23CBC70A036BC601530BC784129BC382422BC48BE1ABC0C0F13BCFA160BBC00D602BC9297F4BB64F1E2BBDBF550BBFF00FF00FF00FF00A50000004C555443303000000000100000000000024000000F00000101820243C3C400C4C4C505030F06040B0E090D0A080CC0C1050201078F922449B01F685AB6BF11B5E4756FD5912B264478BF9C87567EFB3058FF12DFCB7F187BE43DB525F09F39F2C69EA25A263C630D783F35B1979F07196DCF099C13CFB500B44FDB88037CA4B1BF7F047890FBA34DD3F1C92876F5E7F8B7EA477021F8830DD9F6B3A5EFF4511D78EF477367FD39D9187ECE02C3FAA45EE4E867AEBC93CFE00AC69FD57EA11F3CE2FE7E10E44AFE58F16CF94077AE7DA59C877EB545B2F52B67E0E3AB962DE657B7E6CB6F2DE3E89BC510FF9B3FABB9EFC9B9F57EB983C95FB1F2465F78AFE07FD8CC16BF88AC38BFC0AD8CDF96C52ADF376F85EF7A73E3BBEBC6FBABE4F47D1514A47CF5C2BCFD55244FE77BBA57C3F7C5DAF67BCAA9F6BD4538E59BDBF2C637597DF99BA44EFDCDD77CFF26EC10E93B8C608DEF408E81EF7B6DB9EF372CC6BE6EAECC7CBB96C2FCC5BC73EE31B006FDCC1C597F4408CB5F4DEFF15F0DEBEA7CDA61E57C6B28D8FC2F684FF51764E3B617348FE82F0C66FD1760E7CD515A31E2475D6CC7A3B0CE001E1578893C4A15B4E6A80C85CDA316A7A98F32313B8F5A12F45167C976D422593CEA90D07DD42A761F75E2DC8F7A636CA336D5BB63D6EDE931E7D98098C5B4EEE6ADD5F9E6FBE63CE6D9593A664C1C3C6630D03D7CFEBE38F1A2A17D8F0F1CE9FCF87BECFAC7CF5D0F73BCE9ADC451B456C351B23EFA28383EFF281B9DF9A3A449AC4741C80147817DC111E76EC41163EDE688F70FF388532678C488ABED18CA7CEF635C44F3313042E431D409D6630CF8D663985AF8716B2F90E3C630E48F5B77D98E7B6668C76D5FCC1E5588481C35615F3EAA47838F8A05EC8FBAB9A03EEA0B0071D4865AE2A8948AF8A8B2C6DCF19318E9F10263DCC7A9ECDFF1CB83E0E36F6F5AC73C93271C3185F57D63E6F8EC98B20DE33123A5E331754FCB63265CC863E2B5C631610BE71C3D5BEB1C11567C9CC09370383A977938A341E7715031E21F573AFEC7CDAA03E362EDD1E3EE0BC1E3664681C7DDDDCD1F51B2BA3EA29C2E3BE2E9917944B4D37DB40C877634954BF96888A1EE083FC3F111EEEC790440ACF04DD730B19B227008DD7478B4FA261486E44DCB0DF34D8B75D74DEB987C6F7AAF2DDC34EF1EBBE52CDA6F7998B4DCF20173DE329A0F73FB171FC3ED916686DBC86ED13772BAC09B0405746ED6A73BDFB165C81B9911F286DB2A73C379B5BF616CC5EF1646B6EE5B017AFD2DEDCF296EF6B6B0B8EDD5C0DCA6D257BB69D673F9A968DCBF69683DBB53D56EBB4D0F5475371D5CC137C589DB6E0ABAF5DE4E8B89CEEDAE7CE9DBC924C6ED02C3E2761BF6ED76A7D9CDDB8D84CADB998618B7CC8BEC5BEE8D10B7DC47CCDE469041DF062F2EDE2647D3BB0D4CC3765BC1A6BF6DEAE17F5BD85EE21B6254E71BE6EEE49B699FB19B05F1C26E86CE01BEC1D37ABC41AC61FA408589FD4E2DD2F02A5F6BD8EB7DABE475893AB6EB37725EAEA2D9A25C0A5BE6BAA79D39F54F3F30F73F0D0AD57F3903457EC7A951F513A584EB27B365EB87435F44BFD08616FD22E700FDB6AC62FD6DBBB8FE54346CFA53C53DFD296E29FA9D86D8EA771148ACDFE57A57BF33CE71FDF2D1A1FAE5CD70F5CB72AED62F04D6D76F7388A2DF0D62857E6F9519FA7E7B1BD1FD76EB8BFA6DE62CFA2DEABDE9B700A2AB1FE651A11FE2C8573FDC200DFD306379F5C3DD61F543D096D0CFF405443F3B5FA77E86850CFD6C32D3F433ADE8D0CF8603A99F0CB2887E07DA52FD073AF3EA0FF2ECEAFDE083D2F403492CEA07785FD50F22ABAA1FC4624B3FD8A2BEFAC19EBFAA1FA8E211FD400DADFA81544CF4033467D50F6C44D10FEC0DA21FD8DAAB1F88BD573F00AF493F07582BFD7E2097E8E907FF8AD20F7236AF7EA0A550FD0C7650F5330B67D5CF16B5D5CF66AD573FBBF84A3F534456F5B36511D5CF4CF9AA9F876827FD9F2D68E97EA0AAAAF5833CA8AA1FAC46AB7E80B65BF403B0DAABA70439AB9ECA44547AEAC25BA5A72A26AB9ED486AD7A53275BF44F656AD5EAA95548D153B8B1AF9E3203AC7A6AED2B7AEAAC91E8A97FB3D5536353A5A70E8C959E5AEF537AEA4DE7D5530384E8A96B13D5537C5CD533333649CFF336143DE6145E3DCC9B557A66C378F5E7A5287A9ECF0BAB3D8FF5AE7A7E6F11D5F387214ACFAFE447F5BC4DABD253F4605B3DE59C247A4A3239ABA7C522AF9EB1CE573D896F203D13C762E94F7C19D24FBCA7559E18744B3D23EB963D035F56EA199A2AD23366B755CF30C8D573E7BCE9B9716CD273EB68AB9E7B15AF9E1B02969EAA632D7AEA7343F454312DD153231E544FD5AB457A6AA299E8A90A8BA2A7A747AB9EBCDF889E795853F5797BDBEAF36EABE8E7CD8ED5CFC33DA23D0F5454E999FA2E54CF7C6E5B3D13AFA47AE646AAD5130116347DA4432D7DB4ACCCFAE8076AFAE4FA30F5C95750D5E723929A3E8FC482EA3E8232A67DF0B7ADFAE08B10E88341A2D12704ABA54F5C64559FB09CA5CFCEB7597D76ECB3FAEC4C4AEAB3ED12591FD599571FCD60667DF46CABFAA806A6F451EECCA28F55C1AA8FA8EE571FD1D36BFAA387B5F43E7A21E97DF424B3D5474F20561FD5B4A83EAAF9853EBA37ACF4D118E6D447F190AC8F4A96963EFADA2AFA68F1B0EAA37D20E9B376484B9F5BEF567D0914913E277487F49F3836D57D30024AFA60C552FAE08C47F491D5A9A58FE09347FADC6654E9B31B3ED557E373D657876DFAEAADBAFA6A3D23F5D57947F5D598DCAA6FD62153DF7C5352DFBCC690BE795B4DF4BDC7C5D4F7153991BE2B635AF55FFC09E9BE78B54C002449924C555443303000000000100000000000024000000F00000101420243C3C4C400C4C505030F06040B0E090D0A0C08C0C105020107478149BC11E7C8011163FDC188B76AC48873A9E6C4880BF318CB2478637CAAE931307CEF319664F3630C42E4631009DE716BF8DEE3C653F88F7B3F908E7B30E4C74D55991E7744481C37578C3EAE88488F8B61578FBB67833E6E05E871DCB9A0E2B80A00F8B8845AD4B1968BEDB1F2C6DCC79298D7B10263E063ADEC7AC7CA83271C4B4FF77D2C92F8E8318709E363E6A7E398B24BCB312354C83157B5C663260FE763E25BEF31615E7C1C3D93701C1995799CC061E7383B31E238A33BFE7170AB031F75EDD147CD0AC1A3E24681A3EE55CDA366A2AB4755D42A1F71E9993EA2A4DA3A620C857944954A7DA488B174A42FC2F948AAA8EA0840ACF111D73079042270F0695678A1D33414889D498FA6FA49CB86E449EF09F34F5A57DF9C34905C3AE52B294F79EB1E9CF228D29E32D0B473FA0173C3E99B0F86D3151FD127D966C093886E764E52AB3B9F0405C813D6B5F284316573C299113F61DA2BEB1459A7EE53ECC5FD2946F62D4E01FBA038ED4FC09CF6A65F3A6DDD53F9B4D3DC3F6DD62D3AAD686E3A6DE87677DA9DD4C1690B89DAA71DBBF7A7C50BC94E0BBE7C9E4AC924CEA90243E9531BB6C6A9B599E254CD86E9549106CD53CC8ACB53EE8D18A7D447EC53669010A7062B8C9E2667419F0D4C2A9E52C1DA3A69EAC27452D8B43F13E2E17F13A656E2136D56E71305EAE44F849FA14E905380DBB66DDBF41EB76D4E613F90AB697F2388C8EFDE0F235F4C61B05E393EA9BCF6B4B07E254B96BF30E4C97A6EB5E03F73120C3D65E24D788632F07E6E382B3F0B019A9E1311279E4AE34D9FB4F006F84CD35EFF0C5120F747F1A5E393E0A8EACF13EEDD8F6F43F0073A32E967A656EDB3B2F1D6CF05CEFA53AD20FC147C85F7C9C1C9D9CFBA59259F78148C3F20BC623FA1C47DFD814895FC4EE3D9F26EEF54BA75388FBD55CB64EFABCEC0C7D73C52CC35EFCD953553C6D9D70B21FEBD7E7453AF92736BAE520593BFE265CD5EF156C15E311129AF117971AE817B19D72D8A57756BDE0B75B5A6C62EDE8DF76E49E9BABA3848B9B58659FB6B49D6CEB576AB865A8A35E9359773E96BCA70CA3537658D9AA3BAF24D489DFA75BEB97ED7D921DBD719C11BD7811C035DF5DB52B96A500C79D55499D4552987FA8A79E7BE62600DAF9839B2AF881094B992D6E3B9125EDD79A5C2CBEE9570A04D5798D6D92BC8C6FB2B6C1E9A5718CCC42BC0CE8EE3F462018EBBD012C7619DE83D2EF00B79DC2ECECD7119429BC72924521F4792771EF5B2E8A3CEA1E9A845E878D421A9FBA857D03EEAC4751FB5C6D2474DAB01C7BCD2D563CEA3F3310BE979CC7BAA76CC75CD78CCB3F37ACC983871CC40B0FBF8FC5DDBE36563D01F1F38AAF8F1F5DAF58F9F6C1FE678645289A370A886A3367CF451C97DFE51823AF347730EEB8E66CDBB3D3361AC7BF35B943DCF6705DD9EC75A753DBFB7C8EEF9C290B7E755B2B37B9E26DDED29FA30E99E726A933D25991CDD534291754F58E7EF9EC427D89E8943F1F627AE8CED27D6D2BB4F0CBBB79E91776F9E812BEFF78CCDDDED19A37BBB6710E4EEB973DEF6DC38F6EDB977F477CFAD8B75CF0D816FCFD5B1963DF739217BAE909EECB9910FBBE7EED5B23D379148F65C0545D973D2A377CFD66B64CF2CBCB97BACBD49F759B557F6B36687EE67E11ED99E052BBBF64C5DDFBB673EF7E99E8975DB3D73239DEE89000BD23EDBA1DE3E5A5EE67D7482A57D725D98FBE42FECEE73916D699F474261F71F4119DA3EF89B747D7045C8F6C130D9EC138257DB272AB2BB4F50CEDB67E7DAE83E3BF4D17D76A625F7D9F489BCCF4ECCBACF6630F33EFB26DD7D560373FB2C7766D967AEE0DD6776F5BACF6C69A57DD9C27AFB9FADD8F63E5B9279EEB335D8BACF6E92769FDD5C629FDD1B74FB6CCC73EEB37848DE67254F6F9F7DED957D365878F7D92ED8F6D93BA6B7CFAD75EF3E048A6C9F13BB63FB4F1CD3EE3E1801B77DF0E2ED7D70C6B3FB88EADCDB47706DB37D4EA3EEF6D18DD7EEAA7139EFAA43A65DF5D6D55DF59691BBEAACB3BB6ACCEEDD35EF90B96B3E29B96BDE636CD7ACBD24BB5EA362EEFA8A946CD79521BDBB8A9BBE776DDBB6EDEF71DBB606ED034926F43BF148C2EF16AD41BFA7BD92DF7DEE98BEF5C879F926448AF2D56C99EF8B76E6DC2FFDC0D4D7342C762FE50C94BD1DA7C67D4B96127B97CC16DD170E7DBDBD621BBEF68A9C92F6DAA25AF7B5A902FB5AD188ED6B17E3F6B5B831EC551AB4BA5745A4F15E9543D5BD8A20C7F7CA6BC7EE953B42DD2B47A97AAF24587FAFC921CA5E1388177B4D5D66EC35E969642FD2AD2F7BA599F3F6A5A8B7EE9702C8EE5E9867B75E8823EBBD7083C4F6C20CD5DD0B5535DD0B4167622FD20790BDE8589D7B111632F6A27D4CDA8B16A2632FCA0EE45EA4C8227B116C6FF722E8CCBA17C8A3BA17820F6E2F0B24F1F617E07DD92F88BCBB5E108A77BD60CBEEEE057BBEEE5EB0BB47F682BDF4EE058B21D90B369C772F5811652FD837C85EB06FEB5EB0F6D6BD60ACB4BD20E0E9F602817CB21717FC2A7B2FC899B67B81DE6EF722D0ADDD8B2860772F52C0742F9A9DD6BDA894BABD68B5D1DD8BE245762F12E5EF5E9422D5F6A2A4A0B717C1EEEE5E0BF2B07B5EA09BDD7B0192EED90B80BEEB9E1B6CBC7B2E6FD9EDB9E7EFDD9E1398BC7B0E1BF6EEB9956CD97397A977CFE774B13DCFE1C6BB7B8E0864EEA9B7AFECA9F3F2B2A77EA9744F8D65DD9E3A88747BEACDCFEDA9339D754FAD10B2A72649764F0D5177CFAC98B63DF39B50F6CC0000F0CC",
            [ 0.0249999985, 5.0, 1, 1.0, 1.0, 1.0, 1.0, 1, 0.0, 1.0, 1.0, 1.0, 1.0, 100.0, 60.0, 96000.0, 0.5, 0.0, 1, 1, 0.0025, 0.5, 0.4, 10.0, 60.0, 0.0, 0.0, 1 ],
            [ 1, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 255, 255, 255, 255, 0, 0, 0, 0 ],
            [ 3, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 3, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 255, 255, 255, 255, 0, 0, 0, 0 ]
        ),
        Template(
            "PLvsPW", 
            {
                "Object (Transparent)": ["759FE5F3", 1],
                "Map": ["F1697E54", 3],
            },
            "41545243303100000C000000E4010000003C800099FF07000080BF000080BF91FF000000",
            "4D5452433030000018000000000000000000000000000000410700000E01000000F0033013900202F8C00FF00EF020F032F044CDCC4C733E5003F0625084803F7003B098C0D0A7F0A600009A26337D00",
            [ 0.0249999985, 5.0, 1, 1.0, 1.0, 1.0, 1.0, 1, 0.0, 1.0, 1.0, 1.0, 1.0, 100.0, 60.0, 96000.0, 0.5, 0.0, 1, 1, 0.0025, 0.5, 0.4, 10.0, 60.0, 0.0, 0.0, 1 ],
            [ 1, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 255, 255, 255, 255, 0, 0, 0, 0 ],
            [ 3, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 3, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 255, 255, 255, 255, 0, 0, 0, 0 ]
        ),        
    ]

def get_templates():
    return templates
    
def get_template_by_name(name):
    for template in templates:
        if template.name == name:
            return template

    return None    
